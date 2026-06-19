# backend/api_connector/services/auth/handlers/basic.py
import base64

import httpx

from api_connector.services.auth.base import BaseAuthHandler


class BasicAuthHandler(BaseAuthHandler):
    """
    Handles AuthType.BASIC authentication.

    Expected credentials dict keys:
      username (str, required)
      password (str, required)

    Note: Base64 is encoding, NOT encryption. The Authorization: Basic header
    must never appear in logs. RFC 7617 allows any characters in username/password
    — no URL encoding is required.

    Security: password must not appear in any log line.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        username: str = credentials["username"]
        password: str = credentials["password"]

        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")

        headers = dict(request.headers)
        headers["Authorization"] = f"Basic {encoded}"
        return httpx.Request(
            method=request.method,
            url=request.url,
            headers=headers,
            content=request.content,
        )
