# backend/tests/test_encryption.py
import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured

from api_connector.services.encryption import EncryptionService

# ── Round-trip tests ──────────────────────────────────────────────────────────


def test_encrypt_decrypt_ascii():
    service = EncryptionService()
    plaintext = "hello world"
    assert service.decrypt(service.encrypt(plaintext)) == plaintext


def test_encrypt_decrypt_unicode():
    service = EncryptionService()
    plaintext = "héllo wörld 🎉"
    assert service.decrypt(service.encrypt(plaintext)) == plaintext


def test_encrypt_decrypt_dict():
    service = EncryptionService()
    data = {"client_id": "abc", "client_secret": "xyz", "nested": {"key": 1}}
    assert service.decrypt_to_dict(service.encrypt_dict(data)) == data


def test_two_encryptions_produce_different_ciphertexts():
    """Fernet uses random IVs — same plaintext produces different ciphertexts."""
    service = EncryptionService()
    ct1 = service.encrypt("same text")
    ct2 = service.encrypt("same text")
    assert ct1 != ct2
    # But both decrypt correctly
    assert service.decrypt(ct1) == "same text"
    assert service.decrypt(ct2) == "same text"


def test_decrypt_garbage_raises_invalid_token():
    """EncryptionService does NOT swallow InvalidToken — callers handle corruption."""
    service = EncryptionService()
    with pytest.raises(InvalidToken):
        service.decrypt("this-is-not-a-valid-fernet-token")


# ── Configuration error tests ─────────────────────────────────────────────────


def test_missing_encryption_key_raises_improperly_configured(settings):
    """Each test uses a fresh EncryptionService instance to avoid cached _fernet."""
    settings.ENCRYPTION_KEY = ""
    service = EncryptionService()
    with pytest.raises(ImproperlyConfigured, match="ENCRYPTION_KEY"):
        service.encrypt("anything")


def test_invalid_encryption_key_raises_improperly_configured(settings):
    settings.ENCRYPTION_KEY = "not-a-valid-fernet-key"
    service = EncryptionService()
    with pytest.raises(ImproperlyConfigured, match="ENCRYPTION_KEY"):
        service.encrypt("anything")


# ── Key-rotation primitives (ADR-005) ──────────────────────────────────────────

# Two distinct, well-formed Fernet keys for these tests.
KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


def test_validate_key_accepts_valid_key():
    EncryptionService().validate_key(KEY_A)  # must not raise


def test_validate_key_rejects_malformed_key():
    with pytest.raises(ImproperlyConfigured, match="Invalid Fernet key"):
        EncryptionService().validate_key("not-a-valid-fernet-key")


def test_is_decryptable_true_for_matching_key():
    ciphertext = Fernet(KEY_A.encode()).encrypt(b"secret").decode()
    assert EncryptionService().is_decryptable(ciphertext, KEY_A) is True


def test_is_decryptable_false_for_wrong_key():
    ciphertext = Fernet(KEY_A.encode()).encrypt(b"secret").decode()
    # Wrong key must return False, not raise
    assert EncryptionService().is_decryptable(ciphertext, KEY_B) is False


def test_reencrypt_round_trips_under_new_key():
    ciphertext = Fernet(KEY_A.encode()).encrypt(b'{"client_id": "abc"}').decode()
    rotated = EncryptionService().reencrypt(ciphertext, KEY_A, KEY_B)
    # Original key can no longer read it; new key can
    assert EncryptionService().is_decryptable(rotated, KEY_A) is False
    assert Fernet(KEY_B.encode()).decrypt(rotated.encode()) == b'{"client_id": "abc"}'


def test_reencrypt_raises_invalid_token_for_wrong_old_key():
    from api_connector.services.encryption import InvalidToken

    ciphertext = Fernet(KEY_A.encode()).encrypt(b"secret").decode()
    with pytest.raises(InvalidToken):
        EncryptionService().reencrypt(ciphertext, KEY_B, KEY_A)


def test_invalid_token_is_reexported_from_encryption_module():
    """Callers catch decryption failures via our module, not cryptography (ADR-005)."""
    from cryptography.fernet import InvalidToken as FernetInvalidToken

    from api_connector.services.encryption import InvalidToken

    assert InvalidToken is FernetInvalidToken


# ── Singleton verification ─────────────────────────────────────────────────────


def test_module_singleton_is_importable():
    from api_connector.services.encryption import encryption_service

    result = encryption_service.encrypt("singleton test")
    assert isinstance(result, str)
    assert encryption_service.decrypt(result) == "singleton test"
