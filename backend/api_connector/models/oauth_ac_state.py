# backend/api_connector/models/oauth_ac_state.py
from django.db import models


class OAuthACState(models.Model):
    """
    Single-use CSRF state record for one OAuth AC authorization attempt.

    The state field is the CSRF parameter sent in the authorization URL and
    must match what the provider returns in the callback. It also serves as
    the lookup key for the associated profile and PKCE verifier.

    Security (OWASP A07 — CSRF):
    - state is a UUID4 string; guessing is computationally infeasible.
    - used=True is set BEFORE the token exchange to prevent concurrent replay.
    - expired records remain in the table; Phase 8 operations runbook documents cleanup.
    - pkce_code_verifier must NEVER appear in logs.
    - redirect_origin is validated against settings.CORS_ALLOWED_ORIGINS at write time.

    [ASSUMPTION] PKCE is implemented (code_verifier + code_challenge stored here).
    If the target provider does not support PKCE, both fields remain null and the
    token exchange omits the code_verifier parameter.
    """

    connection_profile = models.ForeignKey(
        "api_connector.ConnectionProfile",
        on_delete=models.CASCADE,
        related_name="oauth_states",
    )
    # UUID4 string — the CSRF state parameter included in the authorization URL
    state = models.CharField(max_length=255, unique=True)
    # PKCE RFC 7636 — code_verifier: 96-byte URL-safe base64 (~128 chars)
    # Sent with the token exchange request; NEVER logged.
    pkce_code_verifier = models.CharField(max_length=256, null=True, blank=True)
    # PKCE — SHA256(code_verifier), base64url-encoded, no padding
    # Sent in the authorization URL; safe to log if needed.
    pkce_code_challenge = models.CharField(max_length=256, null=True, blank=True)
    # The frontend origin (e.g. "http://localhost:5173") — used as postMessage targetOrigin.
    # Validated against settings.CORS_ALLOWED_ORIGINS at initiate time.
    redirect_origin = models.CharField(max_length=2048, null=True, blank=True)
    # State is valid for 10 minutes from creation
    expires_at = models.DateTimeField()
    # Set to True immediately before the token exchange — prevents replay attacks
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "api_connector_oauth_ac_state"
        indexes = [
            models.Index(fields=["state"]),
            # Active state lookup: "get the latest unused, unexpired state for this profile"
            models.Index(fields=["connection_profile", "used"]),
        ]

    def __str__(self) -> str:
        # Deliberately omits pkce_code_verifier from string representation
        return (
            f"OAuthACState(profile={self.connection_profile_id}, "
            f"used={self.used}, expires={self.expires_at})"
        )
