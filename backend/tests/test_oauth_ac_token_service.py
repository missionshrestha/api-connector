# backend/tests/test_oauth_ac_token_service.py
"""
OAuthACTokenService unit tests.
All HTTP calls to token endpoints mocked via pytest-httpx.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from api_connector.models import OAuthToken, TokenType
from api_connector.services.encryption import encryption_service
from api_connector.services.oauth_ac_exceptions import (
    REASON_CORRUPT,
    REASON_NO_TOKEN,
    REASON_REFRESH_FAILED,
    REASON_REFRESH_MISSING,
    OAuthACReauthorizationRequired,
)
from api_connector.services.oauth_ac_token import OAuthACTokenService
from tests.factories import ConnectionProfileFactory, OAuthTokenFactory

CREDS = {
    "client_id": "test-cid",
    "client_secret": "test-csecret",
    "token_endpoint": "https://auth.example.com/token",
    "authorization_endpoint": "https://auth.example.com/auth",
}


def make_ac_token(
    profile, access="access_tok", refresh="refresh_tok", expires_delta=None
):
    """Helper: create an OAuthToken record for OAuth AC."""
    expires_at = timezone.now() + expires_delta if expires_delta is not None else None
    return OAuthTokenFactory(
        connection_profile=profile,
        token_type=TokenType.OAUTH_AC,
        encrypted_token=encryption_service.encrypt(access),
        encrypted_refresh_token=(
            encryption_service.encrypt(refresh) if refresh else None
        ),
        expires_at=expires_at,
    )


# ── Cache hit tests ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthACTokenServiceCacheHit:
    def test_valid_non_expiring_token_returned_immediately(self, httpx_mock):
        profile = ConnectionProfileFactory()
        make_ac_token(profile, access="valid_token", expires_delta=None)
        result = OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert result == "valid_token"
        assert len(httpx_mock.get_requests()) == 0

    def test_valid_future_expiry_returned_immediately(self, httpx_mock):
        profile = ConnectionProfileFactory()
        make_ac_token(profile, expires_delta=timedelta(hours=1))
        result = OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert result == "access_tok"
        assert len(httpx_mock.get_requests()) == 0


# ── No token / corrupt token tests ───────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthACTokenServiceNoToken:
    def test_no_token_raises_reauth_reason_no_token(self):
        profile = ConnectionProfileFactory()
        with pytest.raises(OAuthACReauthorizationRequired) as exc_info:
            OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert exc_info.value.reason == REASON_NO_TOKEN

    def test_corrupt_access_token_raises_reauth_reason_corrupt(self):
        profile = ConnectionProfileFactory()
        OAuthTokenFactory(
            connection_profile=profile,
            token_type=TokenType.OAUTH_AC,
            encrypted_token="NOT_VALID_FERNET",
            encrypted_refresh_token=None,
            expires_at=None,
        )
        with pytest.raises(OAuthACReauthorizationRequired) as exc_info:
            OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert exc_info.value.reason == REASON_CORRUPT


# ── Silent refresh tests ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthACTokenServiceSilentRefresh:
    def _make_expired(self, profile, refresh="good_refresh"):
        return make_ac_token(
            profile,
            access="old_access",
            refresh=refresh,
            expires_delta=timedelta(seconds=30),  # within 60s buffer
        )

    def test_expired_token_triggers_refresh(self, httpx_mock):
        profile = ConnectionProfileFactory()
        self._make_expired(profile)
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "new_access", "expires_in": 3600},
        )
        result = OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert result == "new_access"

    def test_after_refresh_new_token_stored_in_db(self, httpx_mock):
        profile = ConnectionProfileFactory()
        self._make_expired(profile)
        httpx_mock.add_response(
            status_code=200,
            json={
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 3600,
            },
        )
        OAuthACTokenService().get_access_token(profile.pk, CREDS)
        record = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_AC
        )
        assert encryption_service.decrypt(record.encrypted_token) == "new_access"
        assert (
            encryption_service.decrypt(record.encrypted_refresh_token) == "new_refresh"
        )

    def test_refresh_no_new_refresh_token_preserves_existing(self, httpx_mock):
        """Provider didn't return a new refresh token — keep the existing one."""
        profile = ConnectionProfileFactory()
        self._make_expired(profile, refresh="original_refresh")
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "new_access", "expires_in": 3600},
            # No refresh_token in response
        )
        OAuthACTokenService().get_access_token(profile.pk, CREDS)
        record = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_AC
        )
        # Original refresh token must still be there — THIS IS THE CRITICAL TEST
        assert (
            encryption_service.decrypt(record.encrypted_refresh_token)
            == "original_refresh"
        )

    def test_refresh_401_raises_reauth_refresh_failed(self, httpx_mock):
        profile = ConnectionProfileFactory()
        self._make_expired(profile)
        httpx_mock.add_response(status_code=401, text="Unauthorized")
        with pytest.raises(OAuthACReauthorizationRequired) as exc_info:
            OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert exc_info.value.reason == REASON_REFRESH_FAILED

    def test_no_refresh_token_raises_reauth_refresh_missing(self):
        profile = ConnectionProfileFactory()
        make_ac_token(
            profile,
            access="old",
            refresh=None,
            expires_delta=timedelta(seconds=30),
        )
        with pytest.raises(OAuthACReauthorizationRequired) as exc_info:
            OAuthACTokenService().get_access_token(profile.pk, CREDS)
        assert exc_info.value.reason == REASON_REFRESH_MISSING


# ── store_tokens tests ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthACTokenServiceStoreTokens:
    def test_store_tokens_creates_record(self):
        profile = ConnectionProfileFactory()
        OAuthACTokenService().store_tokens(
            profile_id=profile.pk,
            access_token="at",
            refresh_token="rt",
            expires_in=3600,
        )
        record = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_AC
        )
        assert encryption_service.decrypt(record.encrypted_token) == "at"
        assert encryption_service.decrypt(record.encrypted_refresh_token) == "rt"
        assert record.expires_at is not None

    @pytest.mark.django_db(transaction=True)
    def test_store_tokens_upserts_no_duplicate_rows(self):
        profile = ConnectionProfileFactory()
        svc = OAuthACTokenService()
        svc.store_tokens(profile.pk, "at1", "rt1", 3600)
        svc.store_tokens(profile.pk, "at2", "rt2", 3600)
        assert (
            OAuthToken.objects.filter(
                connection_profile=profile, token_type=TokenType.OAUTH_AC
            ).count()
            == 1
        )

    def test_store_tokens_none_refresh_with_update_clears_field(self):
        profile = ConnectionProfileFactory()
        OAuthACTokenService().store_tokens(
            profile.pk,
            "at",
            refresh_token=None,
            expires_in=None,
            update_refresh_if_none=True,
        )
        record = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_AC
        )
        assert record.encrypted_refresh_token is None
