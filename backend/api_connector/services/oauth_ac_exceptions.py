# backend/api_connector/services/oauth_ac_exceptions.py
"""
OAuth AC typed exceptions.

OAuthACReauthorizationRequired is the single typed signal that the stored
OAuth AC token cannot be used. Callers (OAuthACAuthHandler, ConnectionTestService)
catch this exception and surface it appropriately:
  - In ConnectionTestService: step 3 fails with "re-authorize via browser" message
  - In future PaginationEngine / DataPreviewService: API returns error_code
    API_CONN_041 with the re-authorize instruction

Security: reason is a controlled string from the REASON_* constants below.
Never populate reason from exception messages or DB values — those may leak
internal state.
"""

# ── Reason constants — machine-readable classification for callers ────────────

REASON_NO_TOKEN = "no_token_stored"
REASON_REFRESH_FAILED = "refresh_token_rejected"
REASON_REFRESH_MISSING = "no_refresh_token"
REASON_CORRUPT = "token_data_corrupt"


class OAuthACReauthorizationRequired(Exception):  # noqa: N818
    """
    Raised when the OAuth AC access token cannot be retrieved or refreshed.

    The user must complete the browser consent flow again (Authorize button).
    Safe to surface to the user — reason is a controlled constant, not raw
    exception content.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason  # One of the REASON_* constants above
        self.message = message  # Plain-English; safe to display to user
