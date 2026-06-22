# backend/api_connector/models/auth_config.py
from django.db import models


class AuthConfig(models.Model):
    """
    Stores Fernet-encrypted credentials for a ConnectionProfile.

    Security requirements (OWASP A02:2021 — Cryptographic Failures):
    - encrypted_credentials MUST NEVER be returned in any API response body.
    - encrypted_credentials MUST NEVER appear in any log line.
    - Access is through EncryptionService ONLY. Direct reads outside of
      EncryptionService constitute a security violation.
    - __str__ and __repr__ must not expose this field.

    Storage format: {"blob": "<fernet-ciphertext-string>"}
    See ADR-004: docs/adr/004-auth-config-encrypted-blob.md
    """

    connection_profile = models.OneToOneField(
        "api_connector.ConnectionProfile",
        on_delete=models.CASCADE,
        related_name="auth_config",
    )
    # Stores {"blob": "<fernet-ciphertext>"} — never access directly outside EncryptionService.
    encrypted_credentials = models.JSONField(default=dict, blank=True)
    # Stores {"field_name": {"is_set": bool}} — computed at write time, never decrypted.
    # This field is PUBLIC METADATA — no encryption needed. Treat as safe to read.
    # Never store credential values here — only field names and boolean presence flags.
    credentials_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_connector_auth_config"

    def __str__(self) -> str:
        # Deliberately omits encrypted_credentials from string representation.
        return f"AuthConfig for profile {self.connection_profile_id}"
