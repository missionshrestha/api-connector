# backend/api_connector/services/connection_test/types.py
"""
Shared types for ConnectionTestService.

StepResult is the common return type from all step methods.
STEP_NAMES constants are the single source of truth for step name strings —
never hardcode "dns_resolution" elsewhere in the codebase.

detail dict schemas per step (frontend StepResultItem renders these):
  dns_resolution pass:     {"hostname": str, "resolved_ips": list[str]}
  dns_resolution fail:     {"hostname": str, "error": str, "suggested_action": str}
  network_connectivity pass:  {"status_code": int, "response_time_ms": int}
  network_connectivity fail:  {"error": str, "url": str, "ssl_error": bool, "suggested_action": str}
  auth_injection pass:     {"auth_type": str, "credentials_present": bool}
  auth_injection fail:     {"auth_type": str, "reason": str, "suggested_action": str}
  http_response pass:      {"status_code": int, "response_time_ms": int, "test_url": str}
  http_response fail:      {"status_code": int|None, "response_time_ms": int, "test_url": str, "suggested_action": str}
  format_detection pass:   {"detected_format": str, "source": str}
  response_sample pass:    {"body_size_bytes": int, "truncated": bool, "body_sample": str}
"""

from dataclasses import dataclass, field

# ── Step name constants ───────────────────────────────────────────────────────

DNS_RESOLUTION = "dns_resolution"
NETWORK_CONNECTIVITY = "network_connectivity"
AUTH_INJECTION = "auth_injection"
HTTP_RESPONSE = "http_response"
FORMAT_DETECTION = "format_detection"
RESPONSE_SAMPLE = "response_sample"

ALL_STEPS: list[str] = [
    DNS_RESOLUTION,
    NETWORK_CONNECTIVITY,
    AUTH_INJECTION,
    HTTP_RESPONSE,
    FORMAT_DETECTION,
    RESPONSE_SAMPLE,
]


# ── StepResult dataclass ──────────────────────────────────────────────────────


@dataclass
class StepResult:
    """
    Result of a single connection test step.

    Security: detail must NEVER contain credential values, raw auth headers,
    or exception tracebacks. Exception messages (not class names or tracebacks)
    are acceptable in detail["error"] only after sanitization.
    """

    name: str
    passed: bool
    message: str
    detail: dict = field(default_factory=dict)
    duration_ms: int = 0
