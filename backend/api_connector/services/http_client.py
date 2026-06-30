# backend/api_connector/services/http_client.py
"""
Synchronous HTTP client for outbound API calls.
Architecture decision: ADR-006 (docs/adr/006-sync-http-client.md)
"""

import logging
import time

import httpx

from api_connector.services.auth.base import BaseAuthHandler
from api_connector.services.http_exceptions import (
    HTTPClientError,
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)

logger = logging.getLogger("api_connector.http_client")


class BaseHTTPClient:
    """
    httpx.Client wrapper with auth injection, structured logging, and typed errors.

    Logging contract (OWASP A09 — Security Logging):
    - Log line: METHOD URL_NO_QUERY_STRING → STATUS_CODE (LATENCY_MS)
    - NEVER log: headers, request body, response body, query string parameters.
    - Query string is stripped from URLs before logging to prevent API key leakage
      when delivery="query" is used (APIKeyAuthHandler).

    ssl_verify:
    - Default is True (enforces TLS certificate verification).
    - Only set to False when ConnectionProfile.ssl_verify is explicitly False.
    - Never derive a False default from any other source (OWASP A07).
    """

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        auth_handler: BaseAuthHandler,
        credentials: dict,
        ssl_verify: bool = True,
        **kwargs,
    ) -> httpx.Response:
        """
        Make an authenticated HTTP request.

        Args:
            method: HTTP method ("GET", "POST", etc.)
            url: Full URL for the request
            auth_handler: Injects auth into the request
            credentials: Decrypted credential dict passed to auth_handler
            ssl_verify: Whether to verify TLS certificates (default True)
            **kwargs: Passed to httpx.Request (headers, params, content, json, etc.)

        Returns:
            httpx.Response for 1xx/2xx/3xx responses.

        Raises:
            HTTPStatusError: for 4xx/5xx responses
            HTTPTimeoutError: for request timeout
            HTTPNetworkError: for connection failure or protocol error
        """
        from api_connector.services.ssrf import validate_url_for_ssrf

        validate_url_for_ssrf(url)  # No-op when SSRF_PROTECTION_ENABLED=False

        # Strip query string before logging — prevents API key leakage
        url_no_qs = url.split("?")[0]

        try:
            request = httpx.Request(method, url, **kwargs)
            authenticated_request = auth_handler.prepare_request(request, credentials)

            start_time = time.monotonic()
            with httpx.Client(verify=ssl_verify, timeout=self.timeout, follow_redirects=True) as client:
                response = client.send(authenticated_request)
            latency_ms = int((time.monotonic() - start_time) * 1000)

            logger.info(
                "HTTP %s %s → %s (%dms)",
                method,
                url_no_qs,
                response.status_code,
                latency_ms,
            )

            if response.status_code >= 400:
                raise HTTPStatusError(
                    f"HTTP {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text[:512],
                )

            return response

        except HTTPClientError:
            # Re-raise our typed errors without wrapping
            raise
        except httpx.TimeoutException as exc:
            logger.warning("HTTP %s %s → TIMEOUT", method, url_no_qs)
            raise HTTPTimeoutError(str(exc), url) from exc
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            logger.warning(
                "HTTP %s %s → NETWORK_ERROR: %s", method, url_no_qs, type(exc).__name__
            )
            raise HTTPNetworkError(str(exc), url) from exc

    def get(
        self,
        url: str,
        *,
        auth_handler: BaseAuthHandler,
        credentials: dict,
        ssl_verify: bool = True,
        **kwargs,
    ) -> httpx.Response:
        return self.request(
            "GET",
            url,
            auth_handler=auth_handler,
            credentials=credentials,
            ssl_verify=ssl_verify,
            **kwargs,
        )

    def post(
        self,
        url: str,
        *,
        auth_handler: BaseAuthHandler,
        credentials: dict,
        ssl_verify: bool = True,
        **kwargs,
    ) -> httpx.Response:
        return self.request(
            "POST",
            url,
            auth_handler=auth_handler,
            credentials=credentials,
            ssl_verify=ssl_verify,
            **kwargs,
        )
