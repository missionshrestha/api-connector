# backend/api_connector/services/auth/handlers/bearer.py
import httpx

from api_connector.services.auth.base import BaseAuthHandler


class BearerAuthHandler(BaseAuthHandler):
    """
    Handles AuthType.BEARER authentication.

    Expected credentials dict keys:
      token (str, required): the bearer token value
      header_name (str, optional, default "Authorization"): header to inject into

    Security: token must not appear in any log line.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        token: str = credentials["token"]
        header_name: str = credentials.get("header_name", "Authorization")

        headers = dict(request.headers)
        headers[header_name] = f"Bearer {token}"
        return httpx.Request(
            method=request.method,
            url=request.url,
            headers=headers,
            content=request.content,
        )
