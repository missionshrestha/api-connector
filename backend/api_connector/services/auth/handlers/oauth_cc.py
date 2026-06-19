# backend/api_connector/services/auth/handlers/oauth_cc.py
import httpx

from api_connector.services.auth.base import BaseAuthHandler


class OAuthCCAuthHandler(BaseAuthHandler):
    """
    Stub for AuthType.OAUTH_CC (OAuth 2.0 Client Credentials).
    Phase 3: implement via OAuthCCTokenService.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        raise NotImplementedError("OAuthCCAuthHandler not yet implemented — Phase 3")
