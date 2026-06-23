# backend/tests/test_oauth_cc_token_service.py
"""
OAuthCCTokenService unit tests.
All HTTP calls to token endpoints are mocked via pytest-httpx.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from api_connector.models import OAuthToken, TokenType
from api_connector.services.encryption import encryption_service
from api_connector.services.oauth_cc_token import (
    OAuthCCTokenFetchError,
    OAuthCCTokenService,
)
from tests.factories import ConnectionProfileFactory, OAuthTokenFactory

VALID_CREDENTIALS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "token_endpoint": "https://auth.example.com/token",
}


@pytest.mark.django_db
class TestOAuthCCTokenServiceCaching:
    def test_cache_hit_valid_token_no_http_call(self, httpx_mock):
        profile = ConnectionProfileFactory()
        # Store a non-expiring token in cache
        OAuthTokenFactory(
            connection_profile=profile,
            encrypted_token=encryption_service.encrypt("cached_token"),
            expires_at=None,
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "cached_token"
        # No HTTP call should have been made
        assert len(httpx_mock.get_requests()) == 0

    def test_cache_hit_future_expiry_no_http_call(self, httpx_mock):
        profile = ConnectionProfileFactory()
        OAuthTokenFactory(
            connection_profile=profile,
            encrypted_token=encryption_service.encrypt("future_token"),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "future_token"
        assert len(httpx_mock.get_requests()) == 0

    def test_cache_expiring_within_buffer_fetches_new_token(self, httpx_mock):
        """Token expiring in 30s (< 60s buffer) → fetch new token."""
        profile = ConnectionProfileFactory()
        OAuthTokenFactory(
            connection_profile=profile,
            encrypted_token=encryption_service.encrypt("expiring_token"),
            expires_at=timezone.now() + timedelta(seconds=30),
        )
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "new_token", "expires_in": 3600},
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "new_token"

    def test_cache_miss_fetches_and_stores_token(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "fresh_token", "expires_in": 3600},
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "fresh_token"
        stored = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_CC
        )
        assert encryption_service.decrypt(stored.encrypted_token) == "fresh_token"
        assert stored.expires_at is not None


@pytest.mark.django_db
class TestOAuthCCTokenServiceFetchErrors:
    def test_token_endpoint_401_raises_fetch_error(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=401, text="Unauthorized")
        with pytest.raises(OAuthCCTokenFetchError) as exc_info:
            OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert "401" in str(exc_info.value)
        assert "client_secret" not in str(exc_info.value)

    def test_missing_access_token_in_response_raises_error(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=200, json={"token_type": "bearer"})
        with pytest.raises(OAuthCCTokenFetchError) as exc_info:
            OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert "access_token" in str(exc_info.value)

    def test_expires_in_absent_stores_null_expires_at(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(
            status_code=200, json={"access_token": "token_no_expiry"}
        )
        OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        stored = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_CC
        )
        assert stored.expires_at is None

    @pytest.mark.django_db(transaction=True)
    def test_second_fetch_overwrites_first_no_duplicate_rows(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=200, json={"access_token": "token_1"})
        OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        httpx_mock.add_response(status_code=200, json={"access_token": "token_2"})
        # Force re-fetch by deleting cached token
        OAuthToken.objects.filter(connection_profile=profile).delete()
        OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert OAuthToken.objects.filter(connection_profile=profile).count() == 1
