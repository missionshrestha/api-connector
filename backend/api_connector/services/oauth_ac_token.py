# backend/api_connector/services/oauth_ac_token.py
"""
OAuth 2.0 Authorization Code token management — retrieval, storage, silent refresh.

Architecture (inline ADR):
  This service is the ONLY place that reads or writes OAuth AC tokens.
  The callback view calls store_tokens() once after the consent flow.
  OAuthACAuthHandler calls get_access_token() for every outbound request.
  No other code may read OAuthToken records for token_type=OAUTH_AC.

Refresh token semantics:
  An OAuth AC profile is "authorized" as long as it has a valid refresh token.
  Even if the access token is expired, get_access_token() silently refreshes it.
  If the refresh token is rejected by the provider (expired or revoked),
  OAuthACReauthorizationRequired is raised — user must re-authorize.

Note: store_tokens() is public (no underscore) — it is called by the callback
view, which lives outside this service.
"""

import logging
import time
from datetime import timedelta

import httpx
from cryptography.fernet import InvalidToken
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

logger = logging.getLogger("api_connector.oauth_ac_token")

# Refresh access token if it expires within this buffer
TOKEN_EXPIRY_BUFFER_SECONDS = 60


class OAuthACTokenService:
    """
    Service for OAuth 2.0 Authorization Code token lifecycle management.
    Stateless — all state persists in the OAuthToken DB table.
    """

    def get_access_token(self, profile_id: int, credentials: dict) -> str:
        """
        Return a valid OAuth AC access token for the given profile.

        Silent refresh path: if the access token is expired or near-expiry,
        use the stored refresh token to fetch a new one silently.

        Args:
            profile_id: ConnectionProfile PK.
            credentials: Decrypted credentials dict from AuthConfig —
                must contain token_endpoint, client_id, client_secret.

        Returns:
            Plaintext access token string.

        Raises:
            OAuthACReauthorizationRequired: no stored token, refresh failed,
                or stored data is corrupt.
        """
        record = OAuthToken.objects.filter(
            connection_profile_id=profile_id,
            token_type=TokenType.OAUTH_AC,
        ).first()

        if record is None:
            raise OAuthACReauthorizationRequired(
                reason=REASON_NO_TOKEN,
                message=(
                    "No authorization found. Use the 'Authorize' button "
                    "on the profile form to complete the OAuth consent flow."
                ),
            )

        # Try to decrypt and return the access token if not expired
        try:
            access_token = encryption_service.decrypt(record.encrypted_token)
        except InvalidToken:
            raise OAuthACReauthorizationRequired(
                reason=REASON_CORRUPT,
                message=(
                    "Stored authorization data is corrupt. "
                    "Re-authorize to reset your credentials."
                ),
            ) from None

        is_valid = (
            record.expires_at is None
            or record.expires_at
            > timezone.now() + timedelta(seconds=TOKEN_EXPIRY_BUFFER_SECONDS)
        )
        if is_valid:
            return access_token

        # Access token expired — attempt silent refresh
        if not record.encrypted_refresh_token:
            raise OAuthACReauthorizationRequired(
                reason=REASON_REFRESH_MISSING,
                message=(
                    "Authorization has expired and no refresh token is available. "
                    "Re-authorize via the 'Authorize' button on the profile form."
                ),
            )

        try:
            refresh_token_plaintext = encryption_service.decrypt(
                record.encrypted_refresh_token
            )
        except InvalidToken:
            raise OAuthACReauthorizationRequired(
                reason=REASON_CORRUPT,
                message="Stored refresh token data is corrupt. Re-authorize to reset.",
            ) from None

        try:
            new_access_token, new_refresh_token, new_expires_in = (
                self._refresh_access_token(refresh_token_plaintext, credentials)
            )
        except _OAuthACRefreshError as exc:
            raise OAuthACReauthorizationRequired(
                reason=REASON_REFRESH_FAILED,
                message=str(exc),
            ) from exc

        # Persist the new access token; preserve existing refresh token if
        # provider did not return a new one (not all providers rotate refresh tokens)
        self.store_tokens(
            profile_id=profile_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=new_expires_in,
            update_refresh_if_none=False,
        )

        return new_access_token

    def store_tokens(
        self,
        profile_id: int,
        access_token: str,
        refresh_token: str | None,
        expires_in: int | None,
        *,
        update_refresh_if_none: bool = True,
    ) -> None:
        """
        Encrypt and upsert access + refresh tokens for the given profile.

        Called from: the callback view (initial store after consent flow).
        Also called internally after a silent refresh.

        Args:
            profile_id: ConnectionProfile PK.
            access_token: Plaintext access token string. NEVER log this.
            refresh_token: Plaintext refresh token string. NEVER log this.
                None if the provider did not return one.
            expires_in: Seconds until the access token expires. None if unknown.
            update_refresh_if_none: When True (default, used by callback view),
                sets encrypted_refresh_token to None when refresh_token is None.
                When False (used by silent refresh), preserves the existing
                encrypted_refresh_token if refresh_token is None.
        """
        defaults: dict = {
            "encrypted_token": encryption_service.encrypt(access_token),
            "expires_at": (
                timezone.now() + timedelta(seconds=expires_in)
                if expires_in is not None
                else None
            ),
        }

        if refresh_token is not None:
            defaults["encrypted_refresh_token"] = encryption_service.encrypt(
                refresh_token
            )
        elif update_refresh_if_none:
            # Explicitly clear the refresh token field when callback provides None
            defaults["encrypted_refresh_token"] = None

        OAuthToken.objects.update_or_create(
            connection_profile_id=profile_id,
            token_type=TokenType.OAUTH_AC,
            defaults=defaults,
        )

    def _refresh_access_token(
        self, refresh_token_plaintext: str, credentials: dict
    ) -> tuple[str, str | None, int | None]:
        """
        POST to the token endpoint with grant_type=refresh_token.

        Returns:
            (new_access_token, new_refresh_token_or_None, new_expires_in_or_None)

        Raises:
            _OAuthACRefreshError: token endpoint rejected the refresh token.
        """
        token_endpoint = credentials["token_endpoint"]

        from api_connector.services.ssrf import validate_url_for_ssrf

        validate_url_for_ssrf(token_endpoint)

        form_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_plaintext,
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        }

        start = time.monotonic()
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    token_endpoint,
                    data=form_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ) as exc:
            raise _OAuthACRefreshError(
                f"Token endpoint unreachable during refresh: {type(exc).__name__}. "
                "Verify the Token Endpoint URL and network connectivity."
            ) from exc

        latency_ms = int((time.monotonic() - start) * 1000)
        # Log ONLY structural metadata — never log refresh_token or response body
        logger.info(
            "OAuth AC token refresh: HTTP %s (%dms)",
            response.status_code,
            latency_ms,
        )

        if response.status_code in (400, 401):
            raise _OAuthACRefreshError(
                "The refresh token was rejected by the authorization server "
                f"(HTTP {response.status_code}). "
                "Re-authorization is required."
            )

        if response.status_code != 200:
            raise _OAuthACRefreshError(
                f"Token endpoint returned HTTP {response.status_code} during refresh."
            )

        try:
            body = response.json()
        except Exception:
            raise _OAuthACRefreshError(
                "Token endpoint returned a non-JSON response during refresh."
            ) from None

        new_access_token = body.get("access_token")
        if not new_access_token:
            raise _OAuthACRefreshError(
                "Token endpoint response missing 'access_token' field during refresh."
            )

        # Some providers return a new refresh token (rotation); accept if present
        new_refresh_token: str | None = body.get("refresh_token") or None
        expires_in_raw = body.get("expires_in")
        new_expires_in: int | None = None
        if expires_in_raw is not None:
            try:
                new_expires_in = int(expires_in_raw)
            except (TypeError, ValueError):
                new_expires_in = None

        return new_access_token, new_refresh_token, new_expires_in


class _OAuthACRefreshError(Exception):
    """
    Internal exception for refresh token rejection.
    Caught by get_access_token(), which converts it to OAuthACReauthorizationRequired.
    Never raised outside this module.
    """
