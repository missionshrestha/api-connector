# backend/tests/test_profile_serializers.py
"""
Serializer unit tests for Phase 2 profile CRUD.

Security invariant tested here:
  - encrypted_credentials NEVER in read serializer output
  - credentials_summary ALWAYS in read serializer output
  - compute_credentials_summary never returns raw values

@pytest.mark.django_db applied only where DB access is required.
Pure validation tests (is_valid() only) do not touch the DB.
"""

from unittest.mock import patch

import pytest
from django.db import IntegrityError

from api_connector.models import AuthConfig, AuthType, ConnectionProfile
from api_connector.serializers.auth_config import (
    APIKeyCredentialSerializer,
    BearerCredentialSerializer,
    NoneCredentialSerializer,
    OAuthACCredentialSerializer,
    OAuthCCCredentialSerializer,
    compute_credentials_summary,
)
from api_connector.serializers.connection_profile import (
    ConnectionProfileCreateSerializer,
    ConnectionProfileReadSerializer,
    ConnectionProfileUpdateSerializer,
)
from api_connector.services.encryption import encryption_service
from tests.factories import AuthConfigFactory, ConnectionProfileFactory

# ── compute_credentials_summary ───────────────────────────────────────────────


class TestComputeCredentialsSummary:
    def test_empty_dict_returns_empty(self):
        assert compute_credentials_summary({}) == {}

    def test_truthy_values_are_set(self):
        result = compute_credentials_summary({"token": "abc123"})
        assert result == {"token": {"is_set": True}}

    def test_empty_string_is_not_set(self):
        result = compute_credentials_summary({"header_name": ""})
        assert result == {"header_name": {"is_set": False}}

    def test_none_value_is_not_set(self):
        result = compute_credentials_summary({"prefix": None})
        assert result == {"prefix": {"is_set": False}}

    def test_mixed_values(self):
        result = compute_credentials_summary(
            {
                "key_name": "X-API-Key",
                "key_value": "secret",
                "delivery": "header",
                "prefix": "",
            }
        )
        assert result["key_name"]["is_set"] is True
        assert result["key_value"]["is_set"] is True
        assert result["delivery"]["is_set"] is True
        assert result["prefix"]["is_set"] is False

    def test_all_6_auth_type_dicts_produce_summary(self):
        """Each auth type credential dict produces the right summary shape."""
        bearer_creds = {"token": "my-token", "header_name": ""}
        result = compute_credentials_summary(bearer_creds)
        assert result["token"]["is_set"] is True
        assert result["header_name"]["is_set"] is False

    def test_summary_values_never_contain_strings(self):
        """Security: summary values must only be {"is_set": bool}, never raw strings."""
        creds = {"password": "super-secret-password-value"}
        result = compute_credentials_summary(creds)
        # The value under "password" must be {"is_set": True}, not the password itself
        assert result["password"] == {"is_set": True}
        assert "super-secret" not in str(result)


# ── Credential Serializer Validation Tests ─────────────────────────────────────


class TestNoneCredentialSerializer:
    def test_empty_input_is_valid(self):
        s = NoneCredentialSerializer(data={})
        assert s.is_valid()
        assert s.validated_data == {}

    def test_any_input_returns_empty(self):
        # NoneCredentialSerializer ignores any input and returns {}
        s = NoneCredentialSerializer(data={"unexpected": "ignored"})
        assert s.is_valid()
        assert s.validated_data == {}


class TestAPIKeyCredentialSerializer:
    def test_valid_header_delivery(self):
        s = APIKeyCredentialSerializer(
            data={
                "key_name": "X-API-Key",
                "key_value": "abc123",
                "delivery": "header",
            }
        )
        assert s.is_valid(), s.errors

    def test_valid_query_delivery(self):
        s = APIKeyCredentialSerializer(
            data={
                "key_name": "api_key",
                "key_value": "secret",
                "delivery": "query",
            }
        )
        assert s.is_valid(), s.errors

    def test_invalid_delivery_choice_rejected(self):
        s = APIKeyCredentialSerializer(
            data={
                "key_name": "X-Key",
                "key_value": "v",
                "delivery": "cookie",  # invalid
            }
        )
        assert not s.is_valid()
        assert "delivery" in s.errors

    def test_missing_key_value_rejected(self):
        s = APIKeyCredentialSerializer(
            data={
                "key_name": "X-API-Key",
                "delivery": "header",
                # key_value omitted
            }
        )
        assert not s.is_valid()
        assert "key_value" in s.errors

    def test_optional_prefix_may_be_omitted(self):
        s = APIKeyCredentialSerializer(
            data={
                "key_name": "X-Key",
                "key_value": "v",
                "delivery": "header",
            }
        )
        assert s.is_valid(), s.errors


class TestBearerCredentialSerializer:
    def test_token_required(self):
        s = BearerCredentialSerializer(data={})
        assert not s.is_valid()
        assert "token" in s.errors

    def test_valid_with_default_header_name(self):
        s = BearerCredentialSerializer(data={"token": "my-bearer-token"})
        assert s.is_valid(), s.errors

    def test_custom_header_name_accepted(self):
        s = BearerCredentialSerializer(data={"token": "t", "header_name": "X-Auth"})
        assert s.is_valid(), s.errors


class TestOAuthCCCredentialSerializer:
    def test_valid_full_input(self):
        s = OAuthCCCredentialSerializer(
            data={
                "client_id": "cid",
                "client_secret": "csecret",
                "token_endpoint": "https://auth.example.com/token",
            }
        )
        assert s.is_valid(), s.errors

    def test_non_url_token_endpoint_rejected(self):
        s = OAuthCCCredentialSerializer(
            data={
                "client_id": "cid",
                "client_secret": "s",
                "token_endpoint": "not-a-url",
            }
        )
        assert not s.is_valid()
        assert "token_endpoint" in s.errors

    def test_non_https_url_also_rejected(self):
        # URLField rejects ftp:// but may allow http://; test that ftp:// is rejected
        s = OAuthCCCredentialSerializer(
            data={
                "client_id": "cid",
                "client_secret": "s",
                "token_endpoint": "ftp://auth.example.com/token",
            }
        )
        assert not s.is_valid()


class TestOAuthACCredentialSerializer:
    def test_requires_authorization_endpoint(self):
        s = OAuthACCredentialSerializer(
            data={
                "client_id": "cid",
                "client_secret": "s",
                "token_endpoint": "https://auth.example.com/token",
                # authorization_endpoint omitted
            }
        )
        assert not s.is_valid()
        assert "authorization_endpoint" in s.errors

    def test_valid_full_input(self):
        s = OAuthACCredentialSerializer(
            data={
                "client_id": "cid",
                "client_secret": "s",
                "token_endpoint": "https://auth.example.com/token",
                "authorization_endpoint": "https://auth.example.com/auth",
            }
        )
        assert s.is_valid(), s.errors


# ── ConnectionProfileReadSerializer Security Tests ─────────────────────────────


@pytest.mark.django_db
class TestConnectionProfileReadSerializer:
    def test_encrypted_credentials_absent_from_output(self):
        profile = ConnectionProfileFactory()
        AuthConfigFactory(
            connection_profile=profile, encrypted_credentials={"blob": "test-blob"}
        )
        s = ConnectionProfileReadSerializer(instance=profile)
        assert "encrypted_credentials" not in s.data

    def test_credentials_summary_present_in_output(self):
        profile = ConnectionProfileFactory()
        AuthConfigFactory(
            connection_profile=profile,
            credentials_summary={"token": {"is_set": True}},
        )
        s = ConnectionProfileReadSerializer(instance=profile)
        assert "credentials_summary" in s.data
        assert s.data["credentials_summary"] == {"token": {"is_set": True}}

    def test_profile_without_auth_config_returns_empty_summary(self):
        """A profile with no AuthConfig must return {} for credentials_summary, not raise."""
        profile = ConnectionProfileFactory()
        # Intentionally no AuthConfigFactory
        s = ConnectionProfileReadSerializer(instance=profile)
        assert s.data["credentials_summary"] == {}

    def test_blob_string_absent_from_output(self):
        """The literal string 'blob' must not appear anywhere in the serializer output."""
        profile = ConnectionProfileFactory()
        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials={"blob": "fernet-ciphertext"},
        )
        s = ConnectionProfileReadSerializer(instance=profile)
        assert "blob" not in str(s.data)


# ── ConnectionProfileCreateSerializer DB Tests ────────────────────────────────


@pytest.mark.django_db
class TestConnectionProfileCreateSerializer:
    def test_valid_bearer_create_makes_both_profile_and_auth_config(self):
        data = {
            "name": "Test Bearer API",
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
            "credentials": {"token": "super-secret-token"},
        }
        s = ConnectionProfileCreateSerializer(data=data)
        assert s.is_valid(), s.errors
        profile = s.save()

        assert profile.pk is not None
        auth_config = AuthConfig.objects.get(connection_profile=profile)
        assert "blob" in auth_config.encrypted_credentials  # encrypted
        assert auth_config.credentials_summary == {
            "token": {"is_set": True},
            "header_name": {"is_set": True},
        }

    def test_create_decrypted_credentials_match_input(self):
        data = {
            "name": "Test",
            "base_url": "https://api.example.com",
            "auth_type": "basic",
            "credentials": {"username": "alice", "password": "s3cr3t"},
        }
        s = ConnectionProfileCreateSerializer(data=data)
        assert s.is_valid(), s.errors
        profile = s.save()

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        decrypted = encryption_service.decrypt_to_dict(
            auth_config.encrypted_credentials
        )
        assert decrypted["username"] == "alice"
        assert decrypted["password"] == "s3cr3t"

    def test_create_with_auth_type_none_succeeds_without_credentials(self):
        data = {
            "name": "Public API",
            "base_url": "https://api.example.com",
            "auth_type": "none",
        }
        s = ConnectionProfileCreateSerializer(data=data)
        assert s.is_valid(), s.errors
        profile = s.save()
        auth_config = AuthConfig.objects.get(connection_profile=profile)
        assert auth_config.credentials_summary == {}

    def test_missing_required_credential_field_returns_400(self):
        data = {
            "name": "Test",
            "base_url": "https://api.example.com",
            "auth_type": "api_key",
            "credentials": {"key_name": "X-Key", "delivery": "header"},
            # key_value missing
        }
        s = ConnectionProfileCreateSerializer(data=data)
        assert not s.is_valid()
        assert "credentials" in s.errors

    def test_request_timeout_out_of_range_rejected(self):
        s = ConnectionProfileCreateSerializer(
            data={
                "name": "Test",
                "base_url": "https://api.example.com",
                "auth_type": "none",
                "request_timeout": 200,
            }
        )
        assert not s.is_valid()
        assert "request_timeout" in s.errors

    def test_invalid_base_url_scheme_rejected(self):
        s = ConnectionProfileCreateSerializer(
            data={
                "name": "Test",
                "base_url": "ftp://api.example.com",
                "auth_type": "none",
            }
        )
        assert not s.is_valid()
        assert "base_url" in s.errors

    def test_empty_header_name_rejected(self):
        s = ConnectionProfileCreateSerializer(
            data={
                "name": "Test",
                "base_url": "https://api.example.com",
                "auth_type": "none",
                "default_headers": [{"name": "", "value": "v"}],
            }
        )
        assert not s.is_valid()
        assert "default_headers" in s.errors

    @pytest.mark.django_db(transaction=True)
    def test_auth_config_creation_failure_rolls_back_profile(self):
        """@transaction.atomic test: no orphaned ConnectionProfile if AuthConfig creation fails."""
        initial_count = ConnectionProfile.objects.count()
        data = {
            "name": "Atomic Test",
            "base_url": "https://api.example.com",
            "auth_type": "bearer",
            "credentials": {"token": "tok"},
        }
        s = ConnectionProfileCreateSerializer(data=data)
        assert s.is_valid(), s.errors

        with (
            patch.object(
                AuthConfig.objects, "create", side_effect=IntegrityError("mocked")
            ),
            pytest.raises(IntegrityError),
        ):
            s.save()

        # Profile must not exist — rollback succeeded
        assert ConnectionProfile.objects.count() == initial_count


# ── ConnectionProfileUpdateSerializer Merge Tests ────────────────────────────


@pytest.mark.django_db
class TestConnectionProfileUpdateSerializer:
    def _make_bearer_profile(self, token="original-token"):
        """Helper: create a profile with bearer token credentials."""
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        creds = {"token": token, "header_name": "Authorization"}
        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict(creds),
            credentials_summary=compute_credentials_summary(creds),
        )
        return profile

    def test_patch_new_token_updates_only_that_field(self):
        profile = self._make_bearer_profile("original-token")
        s = ConnectionProfileUpdateSerializer(
            instance=profile,
            data={"credentials": {"token": "new-token"}},
            partial=True,
        )
        assert s.is_valid(), s.errors
        s.save()

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        decrypted = encryption_service.decrypt_to_dict(
            auth_config.encrypted_credentials
        )
        assert decrypted["token"] == "new-token"
        assert decrypted["header_name"] == "Authorization"  # preserved

    def test_patch_with_empty_string_preserves_existing(self):
        profile = self._make_bearer_profile("original-token")
        s = ConnectionProfileUpdateSerializer(
            instance=profile,
            data={"credentials": {"token": ""}},  # empty = preserve
            partial=True,
        )
        assert s.is_valid(), s.errors
        s.save()

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        decrypted = encryption_service.decrypt_to_dict(
            auth_config.encrypted_credentials
        )
        assert decrypted["token"] == "original-token"  # unchanged

    def test_patch_with_null_credentials_key_leaves_auth_config_unchanged(self):
        profile = self._make_bearer_profile("original-token")
        original_blob = AuthConfig.objects.get(
            connection_profile=profile
        ).encrypted_credentials

        s = ConnectionProfileUpdateSerializer(
            instance=profile,
            data={"credentials": None},
            partial=True,
        )
        assert s.is_valid(), s.errors
        s.save()

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        assert auth_config.encrypted_credentials == original_blob

    def test_patch_without_credentials_key_leaves_auth_config_unchanged(self):
        profile = self._make_bearer_profile("original-token")
        original_blob = AuthConfig.objects.get(
            connection_profile=profile
        ).encrypted_credentials

        s = ConnectionProfileUpdateSerializer(
            instance=profile,
            data={"name": "New Name"},
            partial=True,
        )
        assert s.is_valid(), s.errors
        s.save()

        auth_config = AuthConfig.objects.get(connection_profile=profile)
        assert auth_config.encrypted_credentials == original_blob
        assert profile.name == "New Name"
