# backend/tests/test_exceptions.py
"""
Exception handler tests.
Direct handler tests: no @pytest.mark.django_db needed (no DB access).
Endpoint tests: use client fixture which works without DB for views that don't touch DB.
"""

from rest_framework.exceptions import (
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from api_connector.error_codes import (
    NOT_FOUND,
    PERMISSION_DENIED,
    UNEXPECTED_ERROR,
    VALIDATION_ERROR,
)
from api_connector.exceptions import custom_exception_handler

# ── Direct handler tests (no DB, no view) ─────────────────────────────────────


def test_validation_error_returns_400():
    exc = ValidationError({"name": ["This field is required."]})
    response = custom_exception_handler(exc, {})
    assert response.status_code == 400
    assert response.data["error_code"] == VALIDATION_ERROR
    assert "name" in response.data["detail"]
    assert response.data["detail"] is not None


def test_validation_error_detail_contains_field_errors():
    exc = ValidationError({"email": ["Enter a valid email."], "name": ["Required."]})
    response = custom_exception_handler(exc, {})
    assert "email" in response.data["detail"]
    assert "name" in response.data["detail"]


def test_not_found_returns_404():
    response = custom_exception_handler(NotFound(), {})
    assert response.status_code == 404
    assert response.data["error_code"] == NOT_FOUND
    assert response.data["detail"] == {}


def test_permission_denied_returns_403():
    response = custom_exception_handler(PermissionDenied(), {})
    assert response.status_code == 403
    assert response.data["error_code"] == PERMISSION_DENIED
    assert response.data["detail"] == {}


def test_not_authenticated_returns_401():
    response = custom_exception_handler(NotAuthenticated(), {})
    assert response.status_code == 401
    assert response.data["error_code"] == PERMISSION_DENIED
    assert response.data["detail"] == {}


def test_method_not_allowed_returns_405():
    exc = MethodNotAllowed("DELETE")
    response = custom_exception_handler(exc, {})
    assert response.status_code == 405
    assert response.data["error_code"] == VALIDATION_ERROR
    assert "DELETE" in response.data["message"]
    assert response.data["detail"] == {}


def test_unhandled_exception_returns_500():
    exc = RuntimeError("Something completely unexpected")
    response = custom_exception_handler(exc, {})
    assert response.status_code == 500
    assert response.data["error_code"] == UNEXPECTED_ERROR
    # CRITICAL: traceback must NOT be in the response
    assert "RuntimeError" not in response.data["message"]
    assert "Something completely unexpected" not in response.data["message"]
    assert response.data["detail"] == {}


def test_all_responses_have_required_keys():
    """Structural contract: every response has error_code, message, detail."""
    exceptions = [
        ValidationError({"x": ["err"]}),
        NotFound(),
        PermissionDenied(),
        NotAuthenticated(),
        MethodNotAllowed("PATCH"),
        RuntimeError("boom"),
    ]
    for exc in exceptions:
        response = custom_exception_handler(exc, {})
        assert "error_code" in response.data, (
            f"Missing error_code for {type(exc).__name__}"
        )
        assert "message" in response.data, f"Missing message for {type(exc).__name__}"
        assert "detail" in response.data, f"Missing detail for {type(exc).__name__}"
        assert response.data["detail"] is not None, (
            f"detail is None for {type(exc).__name__}"
        )


# ── Through-endpoint test ─────────────────────────────────────────────────────


def test_post_health_returns_structured_error_envelope(client):
    """Verify the exception handler is correctly wired in settings."""
    response = client.post("/api/health/")
    assert response.status_code == 405
    data = response.json()
    assert data["error_code"] == VALIDATION_ERROR
    assert data["detail"] == {}
    # Confirm it's NOT the old DRF default shape
    assert "detail" in data
    # Old DRF shape has ONLY "detail" as a string — new shape has error_code too
    assert isinstance(data["detail"], dict)
