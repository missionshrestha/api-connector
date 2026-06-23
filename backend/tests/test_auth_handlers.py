# backend/tests/test_auth_handlers.py
"""
Auth handler unit tests. NO @pytest.mark.django_db — these are pure Python tests.
Handlers have no DB access; they only manipulate httpx.Request objects.
"""

import base64

import httpx
import pytest

from api_connector.models.enums import AuthType
from api_connector.services.auth.handlers.api_key import APIKeyAuthHandler
from api_connector.services.auth.handlers.basic import BasicAuthHandler
from api_connector.services.auth.handlers.bearer import BearerAuthHandler
from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
from api_connector.services.auth.handlers.oauth_ac import OAuthACAuthHandler
from api_connector.services.auth.handlers.oauth_cc import OAuthCCAuthHandler
from api_connector.services.auth.registry import (
    auth_handler_registry,
)

BASE_URL = "https://api.example.com/test"


def make_request(**kwargs) -> httpx.Request:
    return httpx.Request("GET", BASE_URL, **kwargs)


# ── NoneAuthHandler ───────────────────────────────────────────────────────────


def test_none_handler_returns_same_request():
    request = make_request()
    result = NoneAuthHandler().prepare_request(request, {})
    assert result is request


def test_none_handler_accepts_any_credentials():
    request = make_request()
    result = NoneAuthHandler().prepare_request(request, {"unexpected": "key"})
    assert result is request


# ── APIKeyAuthHandler ─────────────────────────────────────────────────────────


def test_api_key_header_delivery():
    request = make_request()
    credentials = {
        "key_name": "X-API-Key",
        "key_value": "secret123",
        "delivery": "header",
    }
    result = APIKeyAuthHandler().prepare_request(request, credentials)
    # httpx normalizes header names to lowercase
    assert result.headers["x-api-key"] == "secret123"


def test_api_key_header_with_prefix():
    request = make_request()
    credentials = {
        "key_name": "Authorization",
        "key_value": "abc123",
        "delivery": "header",
        "prefix": "Token",
    }
    result = APIKeyAuthHandler().prepare_request(request, credentials)
    assert result.headers["authorization"] == "Token abc123"


def test_api_key_query_delivery():
    request = make_request()
    credentials = {"key_name": "api_key", "key_value": "mykey", "delivery": "query"}
    result = APIKeyAuthHandler().prepare_request(request, credentials)
    assert "api_key=mykey" in str(result.url)


def test_api_key_query_preserves_existing_params():
    request = make_request(params={"existing": "value"})
    credentials = {"key_name": "api_key", "key_value": "mykey", "delivery": "query"}
    result = APIKeyAuthHandler().prepare_request(request, credentials)
    assert "existing=value" in str(result.url)
    assert "api_key=mykey" in str(result.url)


def test_api_key_invalid_delivery_raises():
    request = make_request()
    credentials = {"key_name": "X-Key", "key_value": "val", "delivery": "cookie"}
    with pytest.raises(ValueError, match="Unknown delivery method"):
        APIKeyAuthHandler().prepare_request(request, credentials)


def test_api_key_original_request_unchanged():
    """Immutability check: original request headers not modified."""
    request = make_request()
    original_headers = dict(request.headers)
    credentials = {"key_name": "X-API-Key", "key_value": "s", "delivery": "header"}
    APIKeyAuthHandler().prepare_request(request, credentials)
    # Original request still has no X-API-Key header
    assert "x-api-key" not in dict(request.headers)
    assert dict(request.headers) == original_headers


# ── BearerAuthHandler ─────────────────────────────────────────────────────────


def test_bearer_default_header():
    request = make_request()
    result = BearerAuthHandler().prepare_request(request, {"token": "mytoken"})
    assert result.headers["authorization"] == "Bearer mytoken"


def test_bearer_custom_header_name():
    request = make_request()
    credentials = {"token": "mytoken", "header_name": "X-Auth-Token"}
    result = BearerAuthHandler().prepare_request(request, credentials)
    assert result.headers["x-auth-token"] == "Bearer mytoken"


def test_bearer_missing_token_raises():
    request = make_request()
    with pytest.raises(KeyError):
        BearerAuthHandler().prepare_request(request, {})


# ── BasicAuthHandler ──────────────────────────────────────────────────────────


def test_basic_auth_header_format():
    request = make_request()
    result = BasicAuthHandler().prepare_request(
        request, {"username": "user", "password": "pass"}
    )
    auth = result.headers["authorization"]
    assert auth.startswith("Basic ")


def test_basic_auth_encoding_is_correct():
    request = make_request()
    result = BasicAuthHandler().prepare_request(
        request, {"username": "alice", "password": "s3cr3t"}
    )
    encoded_part = result.headers["authorization"][6:]  # strip "Basic "
    decoded = base64.b64decode(encoded_part).decode("utf-8")
    assert decoded == "alice:s3cr3t"


def test_basic_auth_special_chars_in_username():
    """RFC 7617: @ and : in username/password do NOT require URL encoding."""
    request = make_request()
    credentials = {"username": "user@example.com", "password": "p@ss:word"}
    result = BasicAuthHandler().prepare_request(request, credentials)
    encoded_part = result.headers["authorization"][6:]
    decoded = base64.b64decode(encoded_part).decode("utf-8")
    assert decoded == "user@example.com:p@ss:word"


# ── OAuth Stubs ───────────────────────────────────────────────────────────────


def test_oauth_cc_raises_value_error_without_profile_id():
    """Stub replaced in Phase 3. Now raises ValueError when _profile_id is missing."""
    request = make_request()
    with pytest.raises(ValueError, match="_profile_id"):
        OAuthCCAuthHandler().prepare_request(request, {})


def test_oauth_ac_raises_value_error_without_profile_id():
    """Stub replaced in Phase 4 — now raises ValueError when _profile_id is missing."""
    request = make_request()
    with pytest.raises(ValueError, match="_profile_id"):
        OAuthACAuthHandler().prepare_request(request, {})


def test_oauth_stubs_instantiate_without_error():
    """Stubs raise NotImplementedError only on prepare_request(), not on instantiation."""
    cc = OAuthCCAuthHandler()
    ac = OAuthACAuthHandler()
    assert cc is not None
    assert ac is not None


# ── AuthHandlerRegistry ───────────────────────────────────────────────────────


def test_registry_returns_correct_handler_types():
    from api_connector.services.auth.handlers.api_key import APIKeyAuthHandler
    from api_connector.services.auth.handlers.basic import BasicAuthHandler
    from api_connector.services.auth.handlers.bearer import BearerAuthHandler
    from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

    assert isinstance(auth_handler_registry.get(AuthType.NONE), NoneAuthHandler)
    assert isinstance(auth_handler_registry.get(AuthType.API_KEY), APIKeyAuthHandler)
    assert isinstance(auth_handler_registry.get(AuthType.BEARER), BearerAuthHandler)
    assert isinstance(auth_handler_registry.get(AuthType.BASIC), BasicAuthHandler)


def test_registry_all_six_types_resolve():
    for auth_type in AuthType.values:
        handler = auth_handler_registry.get(auth_type)
        assert handler is not None


def test_registry_unknown_type_raises_value_error():
    with pytest.raises(ValueError, match="No handler registered"):
        auth_handler_registry.get("completely_invalid_type")


def test_registry_returns_new_instance_per_call():
    """Each call returns a new instance — handlers are stateless."""
    h1 = auth_handler_registry.get(AuthType.NONE)
    h2 = auth_handler_registry.get(AuthType.NONE)
    assert h1 is not h2
