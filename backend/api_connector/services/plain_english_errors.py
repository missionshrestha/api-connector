# backend/api_connector/services/plain_english_errors.py
"""
Plain-English error message registry for ConnectionTestService.

All user-visible messages and suggested actions live here.
NEVER write error messages inline in service code — use this registry.

Phase 8 audit process:
  1. Open this file
  2. Read each `message` and `suggested_action` aloud
  3. Verify: no Python exception class names, no HTTP jargon without explanation,
     no raw internal state, no credential values

Format strings use {keyword} placeholders — call .format(**context) to fill them.
"""

from dataclasses import dataclass


@dataclass
class StepErrorMessage:
    """Structured error message with an actionable suggested next step."""

    message: str
    suggested_action: str


# ── Step error messages keyed by (step_name, failure_reason) ────────────────

STEP_ERROR_MESSAGES: dict[tuple[str, str], StepErrorMessage] = {
    # ── DNS Resolution ────────────────────────────────────────────────────────
    ("dns_resolution", "hostname_not_found"): StepErrorMessage(
        message="Could not resolve the hostname '{hostname}'.",
        suggested_action=(
            "Check for typos in the Base URL, or verify this API is accessible "
            "from this network."
        ),
    ),
    ("dns_resolution", "timeout"): StepErrorMessage(
        message="DNS resolution timed out for '{hostname}'.",
        suggested_action=(
            "The hostname may be blocked by a firewall or DNS resolver. "
            "Try accessing the Base URL from a browser on this machine."
        ),
    ),
    # ── Network Connectivity ──────────────────────────────────────────────────
    ("network_connectivity", "connection_refused"): StepErrorMessage(
        message="Could not connect to {url}.",
        suggested_action=(
            "Verify the Base URL is correct and the API server is running. "
            "Check that the port (if specified) is open."
        ),
    ),
    ("network_connectivity", "ssl_error"): StepErrorMessage(
        message="Security certificate error connecting to {url}. The server's certificate could not be verified.",
        suggested_action=(
            "The server's certificate is invalid or self-signed. "
            "Disable 'Verify SSL Certificate' in the profile if this is expected, "
            "or contact the API provider to fix their certificate."
        ),
    ),
    ("network_connectivity", "timeout"): StepErrorMessage(
        message="Connection to {url} timed out after {timeout}s.",
        suggested_action=(
            "Increase the Request Timeout in the profile, "
            "or check for network or firewall issues between this server and the API."
        ),
    ),
    # ── Auth Injection ────────────────────────────────────────────────────────
    ("auth_injection", "credentials_missing"): StepErrorMessage(
        message="No credentials found for auth type '{auth_type}'.",
        suggested_action=(
            "Open the profile and ensure credentials are saved for this auth type. "
            "Click Edit, fill in the credential fields, and save."
        ),
    ),
    ("auth_injection", "oauth_ac_browser_required"): StepErrorMessage(
        message="OAuth Authorization Code requires browser-based authorization.",
        suggested_action=(
            "Use the 'Authorize' button on the profile form to complete the "
            "OAuth consent flow in your browser before testing the connection."
        ),
    ),
    ("auth_injection", "oauth_ac_reauthorization_required"): StepErrorMessage(
        message="OAuth authorization has expired or was revoked.",
        suggested_action=(
            "Use the 'Authorize' button on the profile form to re-authorize "
            "via your browser. You may need to accept the permissions prompt again."
        ),
    ),
    ("auth_injection", "oauth_cc_token_fetch_failed"): StepErrorMessage(
        message="Could not fetch an OAuth access token from the token endpoint.",
        suggested_action=(
            "Verify the Client ID, Client Secret, and Token Endpoint URL are correct. "
            "Check that the OAuth application has Client Credentials grant type enabled."
        ),
    ),
    ("auth_injection", "credentials_corrupt"): StepErrorMessage(
        message="The stored credentials could not be read. They may have been corrupted.",
        suggested_action=(
            "Open the profile, re-enter your credentials, and save before testing again."
        ),
    ),
    # ── HTTP Response ─────────────────────────────────────────────────────────
    ("http_response", "401"): StepErrorMessage(
        message="The API rejected the credentials (HTTP 401 Unauthorized).",
        suggested_action=(
            "Verify your credentials are correct and have not expired. "
            "For API keys, check the key name and delivery method are set correctly."
        ),
    ),
    ("http_response", "403"): StepErrorMessage(
        message="The API accepted the credentials but denied access (HTTP 403 Forbidden).",
        suggested_action=(
            "Your credentials may have insufficient permissions for this endpoint. "
            "Check the API documentation for required scopes or roles."
        ),
    ),
    ("http_response", "404"): StepErrorMessage(
        message="The test path was not found on the server (HTTP 404).",
        suggested_action=(
            "Try a different test path (e.g. /api/v1/ping or /health), "
            "or leave the Test Path blank to test the base URL."
        ),
    ),
    ("http_response", "5xx"): StepErrorMessage(
        message="The API server returned a server error (HTTP {status_code}).",
        suggested_action=(
            "The API may be experiencing issues. Try again in a moment. "
            "If the problem persists, contact the API provider."
        ),
    ),
    ("http_response", "timeout"): StepErrorMessage(
        message="The authenticated request timed out after {timeout}s.",
        suggested_action=(
            "Increase Request Timeout in the profile settings, "
            "or try a faster-responding test path."
        ),
    ),
    ("http_response", "network_error"): StepErrorMessage(
        message="A network error occurred while making the authenticated request.",
        suggested_action=(
            "Check your network connection and verify the Base URL is reachable. "
            "This may indicate a transient network issue."
        ),
    ),
}


# ── Success message templates (filled by the service) ────────────────────────

DNS_SUCCESS_MSG = "Hostname '{hostname}' resolved to {ip_count} address(es)."
NETWORK_SUCCESS_MSG = "Network connectivity confirmed (HTTP {status_code} received)."
AUTH_SUCCESS_MSG = "Credentials injected successfully via {auth_type}."
HTTP_SUCCESS_MSG = "API responded with HTTP {status_code} in {response_time_ms}ms."
FORMAT_DETECTED_MSG = "Response format detected: {detected_format} (source: {source})."
RESPONSE_SAMPLE_MSG = "Response body captured ({byte_count} bytes)."
