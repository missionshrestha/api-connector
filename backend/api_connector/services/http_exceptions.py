# backend/api_connector/services/http_exceptions.py


class HTTPClientError(Exception):
    """Base class for all HTTP client errors raised by BaseHTTPClient."""


class HTTPTimeoutError(HTTPClientError):
    """
    Raised when the request exceeds the configured timeout.
    Wraps httpx.TimeoutException.
    """

    def __init__(self, message: str, url: str) -> None:
        super().__init__(message)
        self.url = url


class HTTPNetworkError(HTTPClientError):
    """
    Raised on connection failure (refused, unreachable, DNS failure at network level).
    Wraps httpx.NetworkError and httpx.RemoteProtocolError.
    """

    def __init__(self, message: str, url: str) -> None:
        super().__init__(message)
        self.url = url


class HTTPStatusError(HTTPClientError):
    """
    Raised when the server returns a 4xx or 5xx response.
    response_body is truncated to 512 bytes to prevent PII leakage in exception chains.
    """

    def __init__(self, message: str, status_code: int, response_body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body  # First 512 bytes only
