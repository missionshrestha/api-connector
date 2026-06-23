# backend/api_connector/services/auth/handlers/oauth_cc.py
import logging

import httpx

from api_connector.services.auth.base import BaseAuthHandler

logger = logging.getLogger("api_connector.auth.oauth_cc")


class OAuthCCAuthHandler(BaseAuthHandler):
    """
    Handles AuthType.OAUTH_CC (OAuth 2.0 Client Credentials).

    Fetches a cached token via OAuthCCTokenService and injects it as
    Authorization: Bearer <token>.

    The _profile_id convention:
    All callers must include "_profile_id": profile.pk in the credentials dict
    before calling prepare_request(). This key is used to look up cached tokens
    and is NEVER injected into any outbound request header or parameter.

    Security: NEVER log the access_token value.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        # Import inside method to avoid circular imports at module load time
        from api_connector.services.oauth_cc_token import OAuthCCTokenService

        profile_id = credentials.get("_profile_id")
        if profile_id is None:
            raise ValueError(
                "OAuthCCAuthHandler requires '_profile_id' in credentials dict. "
                "Ensure ConnectionTestService (or the caller) adds '_profile_id': "
                "profile.pk to the credentials dict before calling prepare_request()."
            )

        access_token = OAuthCCTokenService().get_token(profile_id, credentials)

        logger.debug("OAuthCC auth injected for profile %s", profile_id)

        headers = dict(request.headers)
        headers["Authorization"] = f"Bearer {access_token}"
        return httpx.Request(
            method=request.method,
            url=request.url,
            headers=headers,
            content=request.content,
        )
