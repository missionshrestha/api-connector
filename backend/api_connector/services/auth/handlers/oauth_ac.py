# backend/api_connector/services/auth/handlers/oauth_ac.py
import logging

import httpx

from api_connector.services.auth.base import BaseAuthHandler

logger = logging.getLogger("api_connector.auth.oauth_ac")


class OAuthACAuthHandler(BaseAuthHandler):
    """
    Handles AuthType.OAUTH_AC (OAuth 2.0 Authorization Code).

    Delegates token retrieval to OAuthACTokenService, which handles both
    returning a cached token and silently refreshing an expired one.

    _profile_id convention:
    All callers must include "_profile_id": profile.pk in the credentials dict
    before calling prepare_request(). Required for token cache lookup.

    On OAuthACReauthorizationRequired:
    The handler re-raises it as-is. Callers (ConnectionTestService,
    future PaginationEngine) are responsible for catching this and converting
    it to the appropriate user-facing message or structured API error.

    Security: NEVER log the access_token value.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        # Deferred import prevents circular dependency at module load time
        from api_connector.services.oauth_ac_token import OAuthACTokenService

        profile_id = credentials.get("_profile_id")
        if profile_id is None:
            raise ValueError(
                "OAuthACAuthHandler requires '_profile_id' in credentials dict. "
                "Ensure the caller (ConnectionTestService or PaginationEngine) "
                "adds '_profile_id': profile.pk before calling prepare_request()."
            )

        # May raise OAuthACReauthorizationRequired — callers must handle this
        access_token = OAuthACTokenService().get_access_token(profile_id, credentials)

        logger.debug("OAuth AC auth injected for profile %s", profile_id)

        headers = dict(request.headers)
        headers["Authorization"] = f"Bearer {access_token}"
        return httpx.Request(
            method=request.method,
            url=request.url,
            headers=headers,
            content=request.content,
        )
