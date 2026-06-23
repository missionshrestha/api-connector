# backend/api_connector/models/oauth_token.py
from django.db import models

from api_connector.models.enums import TokenType


class OAuthToken(models.Model):
    """
    Stores Fernet-encrypted OAuth access (and optionally refresh) tokens.

    Shared by Phase 3 (OAuth CC) and Phase 4 (OAuth AC).

    Security requirements (OWASP A02):
    - encrypted_token and encrypted_refresh_token store Fernet ciphertext ONLY.
    - Raw token strings must NEVER appear in this table, in logs, or in API responses.
    - Access is through OAuthCCTokenService / OAuthACTokenService (Phase 4) ONLY.
    - __str__ and __repr__ must not reference either token field.

    The unique_together constraint enforces one active token per (profile, type) pair.
    OAuthCCTokenService uses update_or_create, so the row is overwritten on refresh —
    no stale token accumulation.
    """

    connection_profile = models.ForeignKey(
        "api_connector.ConnectionProfile",
        on_delete=models.CASCADE,
        related_name="oauth_tokens",
    )
    token_type = models.CharField(
        max_length=10,
        choices=TokenType.choices,
        default=TokenType.OAUTH_CC,
    )
    # Fernet ciphertext of the access token string
    encrypted_token = models.TextField()
    # Fernet ciphertext of the refresh token; null for OAUTH_CC (no refresh token)
    encrypted_refresh_token = models.TextField(null=True, blank=True)
    # null = non-expiring or unknown expiry
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_connector_oauth_token"
        # One active token record per (profile, type) pair — update_or_create enforces this
        unique_together = [["connection_profile", "token_type"]]

    def __str__(self) -> str:
        # Deliberately omits token fields from string representation
        return f"OAuthToken({self.token_type}) for profile {self.connection_profile_id}"
