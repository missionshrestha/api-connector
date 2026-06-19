# backend/tests/test_encryption.py
import pytest
from cryptography.fernet import InvalidToken
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


# ── Singleton verification ─────────────────────────────────────────────────────


def test_module_singleton_is_importable():
    from api_connector.services.encryption import encryption_service

    result = encryption_service.encrypt("singleton test")
    assert isinstance(result, str)
    assert encryption_service.decrypt(result) == "singleton test"
