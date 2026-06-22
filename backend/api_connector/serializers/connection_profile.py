# backend/api_connector/serializers/connection_profile.py
"""
Connection profile serializers.

Three-serializer pattern (per ADR-008 rationale in P2.A-06):
  ConnectionProfileReadSerializer   — list + retrieve responses (no secrets)
  ConnectionProfileCreateSerializer — POST (writes encrypted credentials)
  ConnectionProfileUpdateSerializer — PUT/PATCH (merges credentials, preserves unset)

SECURITY INVARIANT: encrypted_credentials must NEVER appear in any serializer
output. The credentials_summary field (plaintext JSONB from 0002 migration) exists
specifically to avoid touching the encrypted blob on read paths.
"""

import logging

from cryptography.fernet import InvalidToken
from django.db import transaction
from rest_framework import serializers

from api_connector.models import AuthConfig, AuthType, ConnectionProfile
from api_connector.serializers.auth_config import (
    CREDENTIAL_SERIALIZER_MAP,
    compute_credentials_summary,
)
from api_connector.services.encryption import encryption_service

logger = logging.getLogger("api_connector.serializers")


class ConnectionProfileReadSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for list and retrieve endpoints.

    credentials_summary is sourced from AuthConfig.credentials_summary
    (the plaintext JSONB field). Zero crypto operations on read.

    Security check: 'encrypted_credentials' must NOT be in Meta.fields.
    """

    credentials_summary = serializers.SerializerMethodField()

    def get_credentials_summary(self, obj) -> dict:
        """
        Returns the plaintext credentials_summary from AuthConfig.
        Never decrypts — reads the pre-computed JSONB field directly.
        Returns {} if no AuthConfig exists (partial-create failure state).
        """
        try:
            return obj.auth_config.credentials_summary
        except AuthConfig.DoesNotExist:
            return {}

    class Meta:
        model = ConnectionProfile
        fields = [
            "id",
            "name",
            "base_url",
            "auth_type",
            "default_headers",
            "ssl_verify",
            "request_timeout",
            "last_test_at",
            "last_test_outcome",
            "last_test_status_code",
            "last_test_response_time",
            "last_test_detected_format",
            "credentials_summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "last_test_at",
            "last_test_outcome",
            "last_test_status_code",
            "last_test_response_time",
            "last_test_detected_format",
            "created_at",
            "updated_at",
        ]
        # SECURITY: encrypted_credentials is intentionally absent.
        # If you need to verify: assert 'encrypted_credentials' not in Meta.fields


class ConnectionProfileCreateSerializer(serializers.ModelSerializer):
    """
    Write serializer for POST /api/connector/profiles/.

    credentials is write_only — it is never echoed back in any response.
    The @transaction.atomic context in create() guarantees no orphaned
    ConnectionProfile rows if AuthConfig creation fails.
    """

    credentials = serializers.JSONField(required=False, default=dict, write_only=True)

    class Meta:
        model = ConnectionProfile
        fields = [
            "name",
            "base_url",
            "auth_type",
            "default_headers",
            "ssl_verify",
            "request_timeout",
            "credentials",
        ]
        extra_kwargs = {
            "credentials": {"write_only": True},
        }

    def validate_base_url(self, value: str) -> str:
        """Strip trailing slash; require http(s) scheme."""
        value = value.rstrip("/")
        if not (value.startswith("http://") or value.startswith("https://")):
            raise serializers.ValidationError(
                "base_url must start with http:// or https://"
            )
        return value

    def validate_request_timeout(self, value: int) -> int:
        """Enforce 1–120 second range."""
        if not (1 <= value <= 120):
            raise serializers.ValidationError(
                "request_timeout must be between 1 and 120 seconds."
            )
        return value

    def validate_default_headers(self, value: list) -> list:
        """Each header must have a non-empty name string."""
        for header in value:
            if not isinstance(header, dict):
                raise serializers.ValidationError(
                    "Each item in default_headers must be an object with 'name' and 'value' keys."
                )
            if not header.get("name", "").strip():
                raise serializers.ValidationError("Header name cannot be empty.")
        return value

    def validate(self, data: dict) -> dict:
        """Dispatch credentials dict to the per-auth-type validator."""
        auth_type = data.get("auth_type", AuthType.NONE)
        credentials = data.get("credentials", {})

        serializer_class = CREDENTIAL_SERIALIZER_MAP.get(
            auth_type, CREDENTIAL_SERIALIZER_MAP[AuthType.NONE]
        )
        cred_serializer = serializer_class(data=credentials)

        if not cred_serializer.is_valid():
            raise serializers.ValidationError({"credentials": cred_serializer.errors})

        # Replace raw credentials with clean validated_data
        data["credentials"] = cred_serializer.validated_data
        return data

    def create(self, validated_data: dict) -> ConnectionProfile:
        """
        Create ConnectionProfile + AuthConfig atomically.

        The @transaction.atomic context ensures: if AuthConfig creation fails
        for any reason (DB error, constraint violation), the ConnectionProfile
        row is rolled back. No orphaned profiles.
        """
        credentials = validated_data.pop("credentials", {})

        with transaction.atomic():
            profile = super().create(validated_data)
            encrypted = encryption_service.encrypt_dict(credentials)
            summary = compute_credentials_summary(credentials)
            AuthConfig.objects.create(
                connection_profile=profile,
                encrypted_credentials=encrypted,
                credentials_summary=summary,
            )

        return profile


class ConnectionProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Write serializer for PUT/PATCH /api/connector/profiles/{id}/.

    All fields are optional (supports both full PUT and partial PATCH).

    Credential merge contract:
      - credentials key absent from request: existing credentials unchanged
      - credentials == null: existing credentials unchanged
      - credentials == {}: existing credentials unchanged
      - credentials has values: existing + new are merged; falsy new values are skipped
        (empty string = "don't change this field")

    This "omit = preserve" contract is a UX guarantee. Changing it to
    "omit = clear" would silently corrupt existing credentials.
    See ADR inline in P2.A-05 task description.
    """

    credentials = serializers.JSONField(
        required=False,
        allow_null=True,
        default=None,
        write_only=True,
    )

    class Meta:
        model = ConnectionProfile
        fields = [
            "name",
            "base_url",
            "auth_type",
            "default_headers",
            "ssl_verify",
            "request_timeout",
            "credentials",
        ]
        extra_kwargs = {
            field: {"required": False}
            for field in [
                "name",
                "base_url",
                "auth_type",
                "default_headers",
                "ssl_verify",
                "request_timeout",
            ]
        }

    def validate_base_url(self, value: str) -> str:
        value = value.rstrip("/")
        if not (value.startswith("http://") or value.startswith("https://")):
            raise serializers.ValidationError(
                "base_url must start with http:// or https://"
            )
        return value

    def validate_request_timeout(self, value: int) -> int:
        if not (1 <= value <= 120):
            raise serializers.ValidationError(
                "request_timeout must be between 1 and 120 seconds."
            )
        return value

    def validate_default_headers(self, value: list) -> list:
        for header in value:
            if not isinstance(header, dict):
                raise serializers.ValidationError(
                    "Each item in default_headers must be an object with 'name' and 'value' keys."
                )
            if not header.get("name", "").strip():
                raise serializers.ValidationError("Header name cannot be empty.")
        return value

    def validate(self, data: dict) -> dict:
        """If credentials are provided, validate with the per-auth-type serializer (partial=True)."""
        credentials = data.get("credentials")
        if credentials is not None and credentials != {}:
            # Filter empty strings before validation.
            # Empty string = "preserve existing field", not a value to validate.
            credentials_to_validate = {k: v for k, v in credentials.items() if v}

            if not credentials_to_validate:
                # Every field was empty string — treat as no-op
                data["credentials"] = {}
                return data

            auth_type = data.get("auth_type")
            if auth_type is None and self.instance is not None:
                auth_type = self.instance.auth_type
            auth_type = auth_type or AuthType.NONE

            serializer_class = CREDENTIAL_SERIALIZER_MAP.get(
                auth_type, CREDENTIAL_SERIALIZER_MAP[AuthType.NONE]
            )
            cred_serializer = serializer_class(
                data=credentials_to_validate, partial=True
            )

            if not cred_serializer.is_valid():
                raise serializers.ValidationError(
                    {"credentials": cred_serializer.errors}
                )

            data["credentials"] = cred_serializer.validated_data
        return data

    def update(
        self, instance: ConnectionProfile, validated_data: dict
    ) -> ConnectionProfile:
        """
        Merge credentials with existing encrypted values, then update profile fields.

        Merge logic:
          merged = {**existing, **{k: v for k, v in new.items() if v}}
          → only truthy new values override existing
          → falsy new values (empty string, None) are skipped (preserve existing)
        """
        credentials = validated_data.pop("credentials", None)

        if credentials is not None and credentials != {}:
            try:
                auth_config = instance.auth_config
            except AuthConfig.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "This profile has no credential storage. Please delete and recreate it."
                        ]
                    }
                ) from None

            try:
                existing_creds = encryption_service.decrypt_to_dict(
                    auth_config.encrypted_credentials
                )
            except InvalidToken:
                logger.error(
                    "AuthConfig.encrypted_credentials is corrupt for profile %s",
                    instance.pk,
                )
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Credential data is corrupt. Contact support."
                        ]
                    }
                ) from None

            # Merge: only include new values that are truthy (non-empty)
            merged_creds = {
                **existing_creds,
                **{k: v for k, v in credentials.items() if v},
            }
            auth_config.encrypted_credentials = encryption_service.encrypt_dict(
                merged_creds
            )
            auth_config.credentials_summary = compute_credentials_summary(merged_creds)
            auth_config.save()

        return super().update(instance, validated_data)
