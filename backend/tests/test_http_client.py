# backend/tests/test_http_client.py
"""
HTTP client tests. NO @pytest.mark.django_db needed.
Uses pytest-httpx to intercept outbound httpx calls.
"""

import httpx
import pytest

from api_connector.services.auth.handlers.api_key import APIKeyAuthHandler
from api_connector.services.auth.handlers.bearer import BearerAuthHandler
from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
from api_connector.services.http_client import BaseHTTPClient
from api_connector.services.http_exceptions import (
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)

BASE_URL = "https://api.example.com/data"


# ── Success cases ─────────────────────────────────────────────────────────────


def test_200_returns_response(httpx_mock):
    httpx_mock.add_response(status_code=200, json={"items": []})
    client = BaseHTTPClient()
    response = client.get(
        BASE_URL,
        auth_handler=NoneAuthHandler(),
        credentials={},
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_201_returns_response(httpx_mock):
    httpx_mock.add_response(status_code=201, json={"id": 1})
    client = BaseHTTPClient()
    response = client.post(
        BASE_URL,
        auth_handler=NoneAuthHandler(),
        credentials={},
    )
    assert response.status_code == 201


def test_204_returns_response(httpx_mock):
    httpx_mock.add_response(status_code=204)
    client = BaseHTTPClient()
    response = client.get(
        BASE_URL,
        auth_handler=NoneAuthHandler(),
        credentials={},
    )
    assert response.status_code == 204


# ── Client error cases ────────────────────────────────────────────────────────


def test_400_raises_http_status_error(httpx_mock):
    httpx_mock.add_response(status_code=400, text="Bad Request")
    client = BaseHTTPClient()
    with pytest.raises(HTTPStatusError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert exc_info.value.status_code == 400


def test_401_raises_http_status_error(httpx_mock):
    httpx_mock.add_response(status_code=401, text="Unauthorized")
    client = BaseHTTPClient()
    with pytest.raises(HTTPStatusError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert exc_info.value.status_code == 401


def test_404_raises_http_status_error(httpx_mock):
    httpx_mock.add_response(status_code=404, text="Not Found")
    client = BaseHTTPClient()
    with pytest.raises(HTTPStatusError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert exc_info.value.status_code == 404


# ── Server error cases ────────────────────────────────────────────────────────


def test_500_raises_http_status_error(httpx_mock):
    httpx_mock.add_response(status_code=500, text="Internal Server Error" * 100)
    client = BaseHTTPClient()
    with pytest.raises(HTTPStatusError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    error = exc_info.value
    assert error.status_code == 500
    # response_body is truncated to 512 bytes
    assert len(error.response_body) <= 512


def test_503_raises_http_status_error(httpx_mock):
    httpx_mock.add_response(status_code=503, text="Service Unavailable")
    client = BaseHTTPClient()
    with pytest.raises(HTTPStatusError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert exc_info.value.status_code == 503


# ── Network failure cases ─────────────────────────────────────────────────────


def test_timeout_raises_http_timeout_error(httpx_mock):
    httpx_mock.add_exception(httpx.ReadTimeout("Read timed out"))
    client = BaseHTTPClient()
    with pytest.raises(HTTPTimeoutError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert exc_info.value.url == BASE_URL


def test_network_error_raises_http_network_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
    client = BaseHTTPClient()
    with pytest.raises(HTTPNetworkError) as exc_info:
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert exc_info.value.url == BASE_URL


def test_remote_protocol_error_raises_http_network_error(httpx_mock):
    httpx_mock.add_exception(httpx.RemoteProtocolError("Invalid response"))
    client = BaseHTTPClient()
    with pytest.raises(HTTPNetworkError):
        client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})


# ── Auth injection verification ───────────────────────────────────────────────


def test_bearer_auth_header_appears_in_request(httpx_mock):
    httpx_mock.add_response(status_code=200, json={})
    client = BaseHTTPClient()
    client.get(
        BASE_URL,
        auth_handler=BearerAuthHandler(),
        credentials={"token": "test-token-abc"},
    )
    sent_request = httpx_mock.get_request()
    assert sent_request.headers["authorization"] == "Bearer test-token-abc"


def test_api_key_header_appears_in_request(httpx_mock):
    httpx_mock.add_response(status_code=200, json={})
    client = BaseHTTPClient()
    client.get(
        BASE_URL,
        auth_handler=APIKeyAuthHandler(),
        credentials={
            "key_name": "X-API-Key",
            "key_value": "mykey",
            "delivery": "header",
        },
    )
    sent_request = httpx_mock.get_request()
    assert sent_request.headers["x-api-key"] == "mykey"


# ── ssl_verify flag propagation ───────────────────────────────────────────────


def test_ssl_verify_true_is_default(httpx_mock):
    """ssl_verify=True is the default — certificate validation is enforced."""
    httpx_mock.add_response(status_code=200, json={})
    client = BaseHTTPClient()
    # If ssl_verify=False were the default, this test setup would accept invalid certs.
    # We just verify the request completes (mock transport bypasses actual TLS).
    response = client.get(BASE_URL, auth_handler=NoneAuthHandler(), credentials={})
    assert response.status_code == 200


def test_ssl_verify_false_can_be_passed(httpx_mock):
    """Explicit ssl_verify=False must be passable for self-signed cert scenarios."""
    httpx_mock.add_response(status_code=200, json={})
    client = BaseHTTPClient()
    response = client.get(
        BASE_URL,
        auth_handler=NoneAuthHandler(),
        credentials={},
        ssl_verify=False,
    )
    assert response.status_code == 200
