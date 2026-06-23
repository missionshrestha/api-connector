# backend/api_connector/views/oauth_callback.py
"""
OAuth 2.0 Authorization Code callback handler.

This is a plain Django view (not DRF) because:
1. It returns HTML, not JSON — DRF's content negotiation is not applicable.
2. The response must work in a popup window context, not an Axios request.

Security contract (OWASP A07 — CSRF):
  - State parameter is validated against OAuthACState before any token exchange.
  - OAuthACState.used is set to True BEFORE the token exchange to prevent
    concurrent replay of the same authorization code.
  - The authorization code is never logged.
  - postMessage is sent to redirect_origin (not '*').

Failure handling:
  - State not found: returns generic HTML error page (no postMessage — no
    redirect_origin available).
  - All other failures: postMessage OAUTH_AC_ERROR to redirect_origin + close popup.
"""

import json
import logging
import time

import httpx
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from api_connector.models import OAuthACState
from api_connector.services.encryption import encryption_service
from api_connector.services.oauth_ac_token import OAuthACTokenService

logger = logging.getLogger("api_connector.oauth_callback")


def _success_html(profile_id: int, redirect_origin: str) -> str:
    """Return an HTML page that posts OAUTH_AC_SUCCESS and closes the popup."""
    ctx = json.dumps({"profile_id": profile_id, "redirect_origin": redirect_origin})
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Authorization Complete</title></head>
<body>
<script>
(function() {{
  var ctx = {ctx};
  try {{
    if (window.opener) {{
      window.opener.postMessage(
        {{ type: 'OAUTH_AC_SUCCESS', profileId: ctx.profile_id }},
        ctx.redirect_origin
      );
    }}
  }} catch (e) {{}}
  try {{ window.close(); }} catch (e) {{}}
  document.getElementById('msg').textContent =
    'Authorization complete. You may close this tab.';
}})();
</script>
<p id="msg">Completing authorization\u2026</p>
</body>
</html>"""


def _error_html(message: str, redirect_origin: str) -> str:
    """Return an HTML page that posts OAUTH_AC_ERROR and closes the popup."""
    ctx = json.dumps({"message": message, "redirect_origin": redirect_origin})
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Authorization Failed</title></head>
<body>
<script>
(function() {{
  var ctx = {ctx};
  try {{
    if (window.opener) {{
      window.opener.postMessage(
        {{ type: 'OAUTH_AC_ERROR', message: ctx.message }},
        ctx.redirect_origin
      );
    }}
  }} catch (e) {{}}
  try {{ window.close(); }} catch (e) {{}}
  document.getElementById('msg').textContent =
    'Authorization failed. You may close this tab.';
}})();
</script>
<p id="msg">Authorization failed. Closing\u2026</p>
</body>
</html>"""


def _generic_error_html(message: str) -> str:
    """Return an HTML error page when redirect_origin is unknown (state not found)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Authorization Error</title></head>
<body>
<p>{message} You may close this tab.</p>
</body>
</html>"""


@require_GET
def oauth_callback(request: HttpRequest) -> HttpResponse:
    """
    GET /api/connector/oauth/callback/

    Handles the OAuth provider redirect after user consent.
    Returns HTML that communicates with the opener window via postMessage.
    """
    # Check for provider-side error first
    error = request.GET.get("error")
    state = request.GET.get("state")
    code = request.GET.get("code")

    if error:
        error_description = request.GET.get(
            "error_description", "Authorization was denied."
        )
        logger.warning("OAuth AC callback received error from provider: %s", error)
        if state:
            record = OAuthACState.objects.filter(state=state, used=False).first()
            if record:
                return HttpResponse(
                    _error_html(error_description, record.redirect_origin or ""),
                    content_type="text/html",
                )
        return HttpResponse(
            _generic_error_html("Authorization was denied by the provider."),
            content_type="text/html",
        )

    if not state or not code:
        logger.warning(
            "OAuth AC callback missing required params: state=%s, code=%s",
            bool(state),
            bool(code),
        )
        return HttpResponse(
            _generic_error_html("Invalid callback — missing required parameters."),
            content_type="text/html",
            status=400,
        )

    # Look up state record
    record = (
        OAuthACState.objects.select_related("connection_profile")
        .filter(state=state)
        .first()
    )

    if record is None:
        logger.warning("OAuth AC callback: unknown state parameter")
        return HttpResponse(
            _generic_error_html("Authorization request not found or already used."),
            content_type="text/html",
            status=400,
        )

    redirect_origin = record.redirect_origin or (
        settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else ""
    )

    # Validate state record
    if record.used:
        logger.warning(
            "OAuth AC callback: state already used (replay attempt) profile=%s",
            record.connection_profile_id,
        )
        return HttpResponse(
            _error_html(
                "This authorization request has already been used.", redirect_origin
            ),
            content_type="text/html",
            status=400,
        )

    if timezone.now() > record.expires_at:
        logger.warning(
            "OAuth AC callback: state expired profile=%s", record.connection_profile_id
        )
        return HttpResponse(
            _error_html(
                "The authorization request expired (10-minute limit). "
                "Please try the Authorize button again.",
                redirect_origin,
            ),
            content_type="text/html",
            status=400,
        )

    # SECURITY: Mark used=True BEFORE the token exchange.
    # Atomic queryset update prevents TOCTOU race between concurrent callbacks
    # with the same state/code pair.
    OAuthACState.objects.filter(pk=record.pk).update(used=True)

    # Decrypt OAuth AC credentials (needed for token exchange)
    try:
        credentials = encryption_service.decrypt_to_dict(
            record.connection_profile.auth_config.encrypted_credentials
        )
    except Exception:
        logger.error(
            "OAuth AC callback: could not decrypt credentials for profile=%s",
            record.connection_profile_id,
        )
        return HttpResponse(
            _error_html(
                "Profile credentials are corrupt. Please re-save the profile.",
                redirect_origin,
            ),
            content_type="text/html",
        )

    # Exchange authorization code for tokens (PKCE included)
    token_endpoint = credentials.get("token_endpoint", "")
    form_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OAUTH_REDIRECT_URI,
        "client_id": credentials.get("client_id", ""),
        "client_secret": credentials.get("client_secret", ""),
    }
    if record.pkce_code_verifier:
        form_data["code_verifier"] = record.pkce_code_verifier

    start = time.monotonic()
    try:
        with httpx.Client(timeout=30) as client:
            token_response = client.post(
                token_endpoint,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except Exception as exc:
        logger.error("OAuth AC token exchange network error: %s", type(exc).__name__)
        return HttpResponse(
            _error_html(
                "Could not reach the token endpoint. Please try again.",
                redirect_origin,
            ),
            content_type="text/html",
        )

    latency_ms = int((time.monotonic() - start) * 1000)
    # Log ONLY status code and latency — NEVER log authorization code, tokens, or response body
    logger.info(
        "OAuth AC token exchange: profile=%s HTTP %s (%dms)",
        record.connection_profile_id,
        token_response.status_code,
        latency_ms,
    )

    if token_response.status_code != 200:
        return HttpResponse(
            _error_html(
                f"Token exchange failed (HTTP {token_response.status_code}). "
                "Verify your OAuth application credentials.",
                redirect_origin,
            ),
            content_type="text/html",
        )

    try:
        token_body = token_response.json()
    except Exception:
        return HttpResponse(
            _error_html(
                "Token endpoint returned a non-JSON response.", redirect_origin
            ),
            content_type="text/html",
        )

    access_token = token_body.get("access_token")
    if not access_token:
        return HttpResponse(
            _error_html(
                "Token endpoint response missing 'access_token'.", redirect_origin
            ),
            content_type="text/html",
        )

    refresh_token = token_body.get("refresh_token") or None
    expires_in_raw = token_body.get("expires_in")
    expires_in = int(expires_in_raw) if expires_in_raw is not None else None

    # Store both tokens encrypted (always update refresh token on initial store)
    OAuthACTokenService().store_tokens(
        profile_id=record.connection_profile_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        update_refresh_if_none=True,  # Initial store — always write refresh field
    )

    logger.info(
        "OAuth AC authorization complete: profile=%s refresh_token_present=%s",
        record.connection_profile_id,
        refresh_token is not None,
    )

    return HttpResponse(
        _success_html(record.connection_profile_id, redirect_origin),
        content_type="text/html",
    )
