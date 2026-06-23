# backend/api_connector/services/oauth_cc_token.py
"""
OAuth 2.0 Client Credentials token fetch, cache, and refresh.

ADR (inline): OAuth Token Storage — Database vs. In-Memory Cache
Decision: Database (OAuthToken model)
Rationale: Multi-process Django workers (Gunicorn, uWSGI) have independent memory.
An in-memory cache produces duplicate token fetches per worker, burning quota on
providers that rate-limit token endpoint calls. DB storage guarantees one active
token record across all processes. Cache hit = one SELECT query. Cache miss =
one POST to token endpoint + one INSERT/UPDATE.
Consequences: OAuthToken table must be migrated before first use. Phase 4 AC
tokens use the same table (different token_type value).

Security (OWASP A02):
  - Raw token strings NEVER written to DB, logs, or API responses.
  - Only Fernet ciphertext stored (via encryption_service.encrypt()).
  - Token endpoint response body NEVER logged.
  - This file is the ONLY place httpx is used directly (not via BaseHTTPClient).
    Rationale: the token request IS the auth mechanism; BaseHTTPClient would
    attempt to inject auth into an auth request.
"""

import logging
import time
from datetime import timedelta

import httpx
from django.utils import timezone

from api_connector.models import OAuthToken, TokenType
from api_connector.services.encryption import encryption_service

logger = logging.getLogger("api_connector.oauth_cc_token")

# Refresh token if it expires within this buffer to prevent race conditions
TOKEN_EXPIRY_BUFFER_SECONDS = 60


class OAuthCCTokenFetchError(Exception):
    """
    Raised when the OAuth CC token endpoint cannot be reached or returns an error.
    Message is safe to display to the user — no raw response bodies.
    """


class OAuthCCTokenService:
    """
    Service for OAuth 2.0 Client Credentials token management.
    Stateless — all state persists in the OAuthToken DB table.
    """

    def get_token(self, profile_id: int, credentials: dict) -> str:
        """
        Return a valid OAuth CC access token string for the given profile.

        Cache hit: returns decrypted token from DB (one SELECT).
        Cache miss: fetches new token, stores encrypted, returns token string.

        Args:
            profile_id: ConnectionProfile primary key (used as cache key).
            credentials: Decrypted credentials dict with keys:
                client_id, client_secret, token_endpoint, scopes (optional).

        Returns:
            Access token as a plain string.

        Raises:
            OAuthCCTokenFetchError: if the token endpoint returns an error or
                the response does not contain an access_token.
        """
        # 1. Check cache
        cached = OAuthToken.objects.filter(
            connection_profile_id=profile_id,
            token_type=TokenType.OAUTH_CC,
        ).first()

        if cached is not None and (
            cached.expires_at is None
            or cached.expires_at
            > timezone.now() + timedelta(seconds=TOKEN_EXPIRY_BUFFER_SECONDS)
        ):
            return encryption_service.decrypt(cached.encrypted_token)

        # 2. Fetch new token from endpoint
        access_token, expires_at = self._fetch_token(credentials)

        # 3. Store encrypted token (upsert via unique_together)
        OAuthToken.objects.update_or_create(
            connection_profile_id=profile_id,
            token_type=TokenType.OAUTH_CC,
            defaults={
                "encrypted_token": encryption_service.encrypt(access_token),
                "encrypted_refresh_token": None,
                "expires_at": expires_at,
            },
        )

        return access_token

    def _fetch_token(self, credentials: dict) -> tuple[str, object]:
        """
        POST to the token endpoint and return (access_token, expires_at).
        expires_at is a timezone-aware datetime or None if not provided.

        Security: NEVER log the response body or the access_token value.
        """
        token_endpoint = credentials["token_endpoint"]
        form_data: dict = {
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        }
        if credentials.get("scopes"):
            form_data["scope"] = credentials["scopes"]

        start = time.monotonic()
        try:
            # Use httpx.Client directly — this is the one permitted exception to the
            # BaseHTTPClient rule (token request IS the auth mechanism).
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    token_endpoint,
                    data=form_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.TimeoutException:
            raise OAuthCCTokenFetchError(
                "Token endpoint timed out. "
                "Verify the Token Endpoint URL and your network connectivity."
            ) from None

        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise OAuthCCTokenFetchError(
                f"Could not reach the token endpoint: {type(exc).__name__}. "
                "Check the Token Endpoint URL."
            ) from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        # Log only structural metadata — NEVER log response body or token
        logger.info(
            "OAuth CC token fetch for profile: HTTP %s (%dms)",
            response.status_code,
            latency_ms,
        )

        if response.status_code != 200:
            raise OAuthCCTokenFetchError(
                f"Token endpoint returned HTTP {response.status_code}. "
                "Verify Client ID, Client Secret, and Token Endpoint URL."
            )

        try:
            body = response.json()
        except Exception:
            raise OAuthCCTokenFetchError(
                "Token endpoint returned a non-JSON response. "
                "Verify the Token Endpoint URL is correct."
            ) from None

        access_token = body.get("access_token")
        if not access_token:
            raise OAuthCCTokenFetchError(
                "Token endpoint response did not contain 'access_token'. "
                "Verify the OAuth application has Client Credentials grant enabled."
            )

        expires_in = body.get("expires_in")
        expires_at = None
        if expires_in is not None:
            try:
                expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                expires_at = None

        return access_token, expires_at
