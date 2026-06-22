# backend/tests/conftest.py
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def assert_no_credential_leak():
    """
    Returns a helper that asserts encrypted credential data is absent from a DRF response.
    The string 'blob' is the key in every encrypted JSON object {"blob": "<ciphertext>"}.
    If it appears in any response body, the encrypted credential is being returned.
    """

    def _check(response):
        data_str = str(response.data)
        assert "blob" not in data_str, (
            f"Encrypted credential blob found in API response — "
            f"encrypted_credentials may be leaking. "
            f"Response (first 300 chars): {data_str[:300]}"
        )
        assert "encrypted_credentials" not in data_str, (
            f"'encrypted_credentials' key found in API response. "
            f"Response (first 300 chars): {data_str[:300]}"
        )

    return _check
