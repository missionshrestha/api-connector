# backend/tests/test_oauth_ac_endpoints.py
"""
API integration tests for OAuth AC endpoints.
Token endpoint calls in callback tests mocked via pytest-httpx.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from api_connector.models import AuthType, OAuthACState, OAuthToken, TokenType
from api_connector.services.encryption import encryption_service
from tests.factories import (
    AuthConfigFactory,
    ConnectionProfileFactory,
    OAuthACStateFactory,
)

INITIATE_URL = "/api/connector/profiles/{}/oauth/initiate/"
CALLBACK_URL = "/api/connector/oauth/callback/"
VALID_AC_CREDS = {
    "client_id": "test-cid",
    "client_secret": "test-csecret",
    "authorization_endpoint": "https://auth.example.com/auth",
    "token_endpoint": "https://auth.example.com/token",
}


def make_oauth_ac_profile():
    profile = ConnectionProfileFactory(auth_type=AuthType.OAUTH_AC)
    AuthConfigFactory(
        connection_profile=profile,
        encrypted_credentials=encryption_service.encrypt_dict(VALID_AC_CREDS),
        credentials_summary={k: {"is_set": True} for k in VALID_AC_CREDS},
    )
    return profile


# ── Initiate endpoint tests ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthInitiateEndpoint:
    def test_oauth_ac_profile_returns_authorization_url(self, api_client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        profile = make_oauth_ac_profile()
        response = api_client.get(
            INITIATE_URL.format(profile.pk),
            {"redirect_origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "state" in data
        assert "code_challenge" in data["authorization_url"]
        assert "code_challenge_method=S256" in data["authorization_url"]
        # CRITICAL: verifier must NEVER appear in the authorization URL
        assert "code_verifier" not in data["authorization_url"]

    def test_state_record_created_in_db(self, api_client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        profile = make_oauth_ac_profile()
        api_client.get(INITIATE_URL.format(profile.pk))
        assert OAuthACState.objects.filter(connection_profile=profile).exists()

    def test_non_oauth_ac_profile_returns_400(self, api_client):
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        AuthConfigFactory(connection_profile=profile)
        response = api_client.get(INITIATE_URL.format(profile.pk))
        assert response.status_code == 400

    def test_pkce_verifier_not_in_response(self, api_client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        profile = make_oauth_ac_profile()
        response = api_client.get(INITIATE_URL.format(profile.pk))
        # Security: code_verifier must not appear anywhere in the response
        assert "code_verifier" not in str(response.json())

    def test_redirect_origin_validated_against_cors(self, api_client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        profile = make_oauth_ac_profile()
        # Invalid origin — falls back to first allowed origin
        api_client.get(
            INITIATE_URL.format(profile.pk),
            {"redirect_origin": "https://evil.attacker.com"},
        )
        state = OAuthACState.objects.filter(connection_profile=profile).first()
        assert state is not None
        assert state.redirect_origin == "http://localhost:5173"  # fallback applied


# ── Callback endpoint tests ───────────────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthCallbackEndpoint:
    def _make_state(self, profile, **kwargs):
        return OAuthACStateFactory(
            connection_profile=profile,
            redirect_origin="http://localhost:5173",
            **kwargs,
        )

    def test_happy_path_stores_tokens(self, client, settings, httpx_mock):
        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        profile = make_oauth_ac_profile()
        state_record = self._make_state(profile)
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
        )
        response = client.get(
            CALLBACK_URL,
            {"code": "auth_code_abc", "state": state_record.state},
        )
        assert response.status_code == 200
        assert "text/html" in response.get("Content-Type", "")
        assert "OAUTH_AC_SUCCESS" in response.content.decode()
        # Token stored
        token = OAuthToken.objects.get(
            connection_profile=profile, token_type=TokenType.OAUTH_AC
        )
        assert encryption_service.decrypt(token.encrypted_token) == "at"
        assert encryption_service.decrypt(token.encrypted_refresh_token) == "rt"
        # State marked used
        state_record.refresh_from_db()
        assert state_record.used is True

    def test_unknown_state_returns_400_generic_html(self, client):
        response = client.get(
            CALLBACK_URL, {"code": "code", "state": "unknown-state-xyz"}
        )
        assert response.status_code == 400
        content = response.content.decode()
        # No postMessage — no redirect_origin known
        assert "OAUTH_AC_ERROR" not in content
        assert "OAUTH_AC_SUCCESS" not in content

    def test_expired_state_returns_error_html(self, client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        profile = make_oauth_ac_profile()
        state_record = OAuthACStateFactory(
            connection_profile=profile,
            redirect_origin="http://localhost:5173",
            expires_at=timezone.now() - timedelta(minutes=1),  # expired
        )
        response = client.get(
            CALLBACK_URL, {"code": "code", "state": state_record.state}
        )
        content = response.content.decode()
        assert "OAUTH_AC_ERROR" in content
        assert "expired" in content.lower()

    def test_used_state_returns_error_html_replay_prevention(self, client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        profile = make_oauth_ac_profile()
        state_record = OAuthACStateFactory(
            connection_profile=profile,
            redirect_origin="http://localhost:5173",
            used=True,
        )
        response = client.get(
            CALLBACK_URL, {"code": "code", "state": state_record.state}
        )
        content = response.content.decode()
        assert "OAUTH_AC_ERROR" in content

    def test_provider_error_param_returns_error_html(self, client, settings):
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        profile = make_oauth_ac_profile()
        state_record = self._make_state(profile)
        response = client.get(
            CALLBACK_URL,
            {"error": "access_denied", "state": state_record.state},
        )
        content = response.content.decode()
        assert "OAUTH_AC_ERROR" in content

    def test_missing_code_returns_400(self, client):
        response = client.get(CALLBACK_URL, {"state": str(uuid.uuid4())})
        assert response.status_code == 400

    def test_authorization_code_not_logged(self, client, settings, httpx_mock, caplog):
        """Security: the authorization code must never appear in logs."""
        import logging

        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        profile = make_oauth_ac_profile()
        state_record = self._make_state(profile)
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
        )
        with caplog.at_level(logging.DEBUG, logger="api_connector"):
            client.get(
                CALLBACK_URL,
                {"code": "SENSITIVE_AUTH_CODE_12345", "state": state_record.state},
            )
        assert "SENSITIVE_AUTH_CODE_12345" not in caplog.text

    def test_token_exchange_failure_returns_error_html(
        self, client, settings, httpx_mock
    ):
        settings.OAUTH_REDIRECT_URI = (
            "http://localhost:8000/api/connector/oauth/callback/"
        )
        settings.CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
        profile = make_oauth_ac_profile()
        state_record = self._make_state(profile)
        httpx_mock.add_response(status_code=400, text="invalid_grant")
        response = client.get(
            CALLBACK_URL, {"code": "bad_code", "state": state_record.state}
        )
        content = response.content.decode()
        assert "OAUTH_AC_ERROR" in content
        assert "token" in content.lower()
