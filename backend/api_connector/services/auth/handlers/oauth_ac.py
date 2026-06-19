# backend/api_connector/services/auth/handlers/oauth_ac.py
import httpx

from api_connector.services.auth.base import BaseAuthHandler


class OAuthACAuthHandler(BaseAuthHandler):
    """
    Stub for AuthType.OAUTH_AC (OAuth 2.0 Authorization Code).
    Phase 4: implement via OAuthACTokenService.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        raise NotImplementedError("OAuthACAuthHandler not yet implemented — Phase 4")
