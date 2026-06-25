# backend/api_connector/exceptions.py
"""
Custom DRF exception handler producing the structured error envelope.

Every API error response has exactly this shape:
  {
    "error_code": "API_CONN_001",
    "message": "A human-readable error message.",
    "detail": {}   ← never null; {} when not applicable
  }

Security (OWASP A09 / ASVS 7.4.1):
- 5xx responses return only "An unexpected error occurred." — no tracebacks,
  no exception class names, no internal state.
- The real error is logged at ERROR level with full traceback (server-side only).
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from api_connector.error_codes import (
    NOT_FOUND,
    OAUTH_AC_REAUTHORIZATION_REQUIRED,
    PERMISSION_DENIED,
    UNEXPECTED_ERROR,
    VALIDATION_ERROR,
)

logger = logging.getLogger("api_connector.exceptions")


def _make_error_response(
    error_code: str,
    message: str,
    detail: dict | list | None = None,
    http_status: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """Build the structured error envelope response."""
    return Response(
        {
            "error_code": error_code,
            "message": message,
            "detail": detail if detail is not None else {},
        },
        status=http_status,
    )


def custom_exception_handler(exc, context) -> Response | None:
    """
    DRF EXCEPTION_HANDLER target. Maps exceptions to the structured error envelope.
    Registered in settings.REST_FRAMEWORK["EXCEPTION_HANDLER"].
    """
    # ── OAuthACReauthorizationRequired ────────────────────────────────────────
    # MUST be checked before bare Exception catch below.
    # OAuthACReauthorizationRequired is a subclass of Exception — order matters.
    # Covers: schema_infer, preview, detect_data_root, any future action
    # that calls OAuthACAuthHandler.prepare_request() with expired/revoked tokens.
    try:
        from api_connector.services.oauth_ac_exceptions import OAuthACReauthorizationRequired
        if isinstance(exc, OAuthACReauthorizationRequired):
            return _make_error_response(
                error_code=OAUTH_AC_REAUTHORIZATION_REQUIRED,
                message=exc.message,  # user-safe per Phase 4 design
                detail={"reason": exc.reason},
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
    
        from api_connector.services.ssrf import SSRFProtectionError
        if isinstance(exc, SSRFProtectionError):
            return _make_error_response(
                error_code=VALIDATION_ERROR,
                message=str(exc),
                detail={"protection": "SSRF_PROTECTION_ENABLED is active"},
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        
    except ImportError: 
        pass  # Module not yet available (shouldn't happen in production)

    # ── DRF Validation Error ──────────────────────────────────────────────────
    if isinstance(exc, ValidationError):
        return _make_error_response(
            error_code=VALIDATION_ERROR,
            message="Validation failed. Check the detail field for field-level errors.",
            detail=exc.detail,
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Not Found (DRF) ───────────────────────────────────────────────────────
    if isinstance(exc, NotFound):
        return _make_error_response(
            error_code=NOT_FOUND,
            message="The requested resource was not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    # ── Permission Denied (DRF) ───────────────────────────────────────────────
    if isinstance(exc, PermissionDenied):
        return _make_error_response(
            error_code=PERMISSION_DENIED,
            message="You do not have permission to perform this action.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # ── Not Authenticated (DRF) ───────────────────────────────────────────────
    if isinstance(exc, NotAuthenticated):
        return _make_error_response(
            error_code=PERMISSION_DENIED,
            message="Authentication required.",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    # ── Method Not Allowed (DRF) ──────────────────────────────────────────────
    if isinstance(exc, MethodNotAllowed):
        # exc.method is not always available depending on DRF version
        # extract from exc.detail instead which is always present
        method = getattr(exc, "method", None) or str(exc.detail).strip('"')
        return _make_error_response(
            error_code=VALIDATION_ERROR,
            message=f"Method {method} not allowed.",
            http_status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # ── Django Http404 ────────────────────────────────────────────────────────
    if isinstance(exc, Http404):
        return _make_error_response(
            error_code=NOT_FOUND,
            message="The requested resource was not found.",
            http_status=status.HTTP_404_NOT_FOUND,
        )

    # ── Django PermissionDenied ───────────────────────────────────────────────
    if isinstance(exc, DjangoPermissionDenied):
        return _make_error_response(
            error_code=PERMISSION_DENIED,
            message="You do not have permission to perform this action.",
            http_status=status.HTTP_403_FORBIDDEN,
        )

    # ── Fall through to DRF's default handler ─────────────────────────────────
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    # ── Unhandled exception → 500 ─────────────────────────────────────────────
    # Log the full traceback server-side. NEVER include it in the response.
    logger.exception("Unhandled exception in API view: %s", exc)
    return _make_error_response(
        error_code=UNEXPECTED_ERROR,
        message="An unexpected error occurred.",
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )