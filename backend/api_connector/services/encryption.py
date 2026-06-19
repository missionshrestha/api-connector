# backend/api_connector/services/encryption.py
import json
import logging

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("api_connector.encryption")


class EncryptionService:
    """
    Fernet-based symmetric encryption for credential storage at rest.

    Architecture: ADR-005 (docs/adr/005-encryption-single-call-site.md)
    - All encrypt/decrypt goes through this class.
    - Direct `from cryptography.fernet import Fernet` imports elsewhere are FORBIDDEN.
    - The Fernet instance is created lazily on first use (not at module import)
      to prevent ImproperlyConfigured crashes during `manage.py check`.

    Security (OWASP A02):
    - Key comes from settings.ENCRYPTION_KEY ONLY. No fallbacks, no hardcoded keys.
    - NEVER log plaintext or ciphertext values.
    - Missing or invalid key raises ImproperlyConfigured at first use — never silently.
    """

    def __init__(self) -> None:
        self._fernet: Fernet | None = None

    def _get_fernet(self) -> Fernet:
        """Load the Fernet instance lazily from settings. Raises ImproperlyConfigured if misconfigured."""
        if self._fernet is None:
            from django.conf import settings

            key = getattr(settings, "ENCRYPTION_KEY", "")
            if not key:
                raise ImproperlyConfigured(
                    "ENCRYPTION_KEY setting is required and must be a valid Fernet key"
                )
            try:
                self._fernet = Fernet(key.encode())
            except (ValueError, Exception) as exc:
                raise ImproperlyConfigured(
                    "ENCRYPTION_KEY setting is required and must be a valid Fernet key"
                ) from exc
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """UTF-8 encode and Fernet-encrypt plaintext. Returns URL-safe base64 ciphertext string."""
        fernet = self._get_fernet()
        return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Fernet-decrypt ciphertext string. Returns original plaintext string.

        Raises cryptography.fernet.InvalidToken if ciphertext is corrupt or tampered.
        This exception is NOT caught here — callers are responsible for handling it.
        """
        fernet = self._get_fernet()
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")

    def encrypt_dict(self, data: dict) -> dict:
        """JSON-serialize a dict, encrypt it, and return {"blob": ciphertext}."""
        plaintext = json.dumps(data)
        ciphertext = self.encrypt(plaintext)
        return {"blob": ciphertext}

    def decrypt_to_dict(self, blob: dict) -> dict:
        """Extract and decrypt a {"blob": ciphertext} dict, returning the original dict."""
        ciphertext = blob["blob"]
        plaintext = self.decrypt(ciphertext)
        return json.loads(plaintext)


# Module-level singleton — loaded once per process.
# All callers: from api_connector.services.encryption import encryption_service
encryption_service = EncryptionService()
