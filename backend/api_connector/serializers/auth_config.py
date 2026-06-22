# backend/api_connector/serializers/auth_config.py
"""
Credential field serializers — one per AuthType.

These serializers are WRITE-ONLY validators. They:
  - Accept a credential dict from the API request
  - Validate field shapes and presence
  - Return validated_data (clean dict)
  - Are NEVER used for serializing output (no read path)

Security (OWASP A02 / ASVS 5.0):
  - token_endpoint and authorization_endpoint are URLField — rejects non-HTTP(S) schemes.
  - max_length limits prevent oversized credential values from being encrypted + stored.
  - Never log validated_data from these serializers.
"""

from rest_framework import serializers

from api_connector.models.enums import AuthType

# ── Utility ───────────────────────────────────────────────────────────────────


def compute_credentials_summary(credentials: dict) -> dict:
    """
    Converts a credential dict to a summary dict of {field_name: {"is_set": bool}}.

    is_set is True when bool(value) is truthy (non-empty string, non-None, etc.).
    An empty dict returns an empty dict.

    Example:
        compute_credentials_summary({"token": "abc", "header_name": ""})
        → {"token": {"is_set": True}, "header_name": {"is_set": False}}
    """
    return {
        field_name: {"is_set": bool(value)} for field_name, value in credentials.items()
    }


# ── Credential Serializers (Write-Only Validators) ────────────────────────────


class NoneCredentialSerializer(serializers.Serializer):
    """No credentials required. Returns {} for any input."""

    def validate(self, data: dict) -> dict:
        return {}


class APIKeyCredentialSerializer(serializers.Serializer):
    key_name = serializers.CharField(max_length=255)
    key_value = serializers.CharField(max_length=2048)
    delivery = serializers.ChoiceField(choices=["header", "query"])
    prefix = serializers.CharField(max_length=100, required=False, allow_blank=True)


class BearerCredentialSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=4096)
    header_name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="Authorization",
    )


class BasicCredentialSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=255)
    password = serializers.CharField(max_length=2048)


class OAuthCCCredentialSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=255)
    client_secret = serializers.CharField(max_length=2048)
    token_endpoint = serializers.URLField(max_length=2048)
    scopes = serializers.CharField(max_length=1024, required=False, allow_blank=True)

    def validate_token_endpoint(self, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("URL must use http or https scheme.")
        return value


class OAuthACCredentialSerializer(OAuthCCCredentialSerializer):
    authorization_endpoint = serializers.URLField(max_length=2048)

    def validate_authorization_endpoint(self, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise serializers.ValidationError("URL must use http or https scheme.")
        return value


# ── Registry Map ──────────────────────────────────────────────────────────────

CREDENTIAL_SERIALIZER_MAP: dict[str, type[serializers.Serializer]] = {
    AuthType.NONE: NoneCredentialSerializer,
    AuthType.API_KEY: APIKeyCredentialSerializer,
    AuthType.BEARER: BearerCredentialSerializer,
    AuthType.BASIC: BasicCredentialSerializer,
    AuthType.OAUTH_CC: OAuthCCCredentialSerializer,
    AuthType.OAUTH_AC: OAuthACCredentialSerializer,
}
