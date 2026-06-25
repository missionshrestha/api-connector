# backend/api_connector/services/encryption.py
import json
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("api_connector.encryption")

# Re-exported so callers (e.g. the key-rotation command) can catch decryption
# failures without importing `cryptography.fernet` directly — keeping ADR-005's
# "Fernet lives only in encryption.py" rule intact.
__all__ = ["EncryptionService", "InvalidToken", "encryption_service"]


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

    # ── Key-rotation primitives (ADR-005) ─────────────────────────────────────
    # Rotation is the one operation that needs TWO keys at once, which the
    # singleton (bound to settings.ENCRYPTION_KEY) cannot express. Rather than
    # let `rotate_encryption_key` import Fernet directly, these helpers keep all
    # Fernet construction in this file. Keys are passed in as strings.

    @staticmethod
    def _fernet_for_key(key: str) -> Fernet:
        """Build a Fernet for an explicit key string. Raises ImproperlyConfigured on a malformed key."""
        try:
            return Fernet(key.encode())
        except (ValueError, Exception) as exc:
            raise ImproperlyConfigured("Invalid Fernet key") from exc

    def validate_key(self, key: str) -> None:
        """Verify a key string is a well-formed Fernet key. Raises ImproperlyConfigured otherwise."""
        self._fernet_for_key(key)

    def is_decryptable(self, ciphertext: str, key: str) -> bool:
        """Return True if ciphertext decrypts under key. Used by rotation dry-runs (never raises InvalidToken)."""
        try:
            self._fernet_for_key(key).decrypt(ciphertext.encode("utf-8"))
            return True
        except InvalidToken:
            return False

    def reencrypt(self, ciphertext: str, old_key: str, new_key: str) -> str:
        """Decrypt ciphertext with old_key and re-encrypt under new_key.

        For key rotation only. Plaintext bytes are never decoded to str or logged.
        Raises InvalidToken if ciphertext cannot be decrypted with old_key.
        """
        old = self._fernet_for_key(old_key)
        new = self._fernet_for_key(new_key)
        return new.encrypt(old.decrypt(ciphertext.encode("utf-8"))).decode("utf-8")


# Module-level singleton — loaded once per process.
# All callers: from api_connector.services.encryption import encryption_service
encryption_service = EncryptionService()
