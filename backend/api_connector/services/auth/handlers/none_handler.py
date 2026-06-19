# backend/api_connector/services/auth/handlers/none_handler.py
import httpx

from api_connector.services.auth.base import BaseAuthHandler


class NoneAuthHandler(BaseAuthHandler):
    """
    No-op auth handler for connections with AuthType.NONE.

    Eliminates the need for 'if auth_handler:' conditionals at call sites.
    One forgotten conditional = one unprotected endpoint.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        return request
