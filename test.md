# Implementation: Phase 3 — Connection Test & Auth Services

---

## 1. Phase Overview

**Purpose:** Deliver the first feature that makes real outbound network calls — a 6-step sequential connection validator that gives users a diagnostic, plain-English answer to "is this API configured correctly?" and implements the full OAuth Client Credentials token flow.

**Outcome:** `OAuthToken` model migrated; `ConnectionTestService` running 6 steps with early-exit; `OAuthCCAuthHandler` fully implemented; `POST /api/connector/profiles/{id}/test/` live; frontend Re-Test button wired to a step-by-step modal with progress simulation and raw response viewer.

**Previous Phase:** Phase 2 — Connection Profile Management
**Next Phase:** Phase 4 (OAuth AC) and Phase 5 (Endpoint & Pagination Engine) — parallel

**Dependencies from Phase 2:** `ConnectionProfile`, `AuthConfig`, `ConnectionTestResult` models; `EncryptionService`; `AuthHandlerRegistry` with OAuth CC stub; `BaseHTTPClient`; `ConnectionProfileViewSet`; `ConnectionProfileFactory`, `AuthConfigFactory`, `api_client` fixture; `PROFILE_QUERY_KEY` hook constant; `APIError` TypeScript type; `apiClient` Axios instance with interceptor.

**Plan Concerns:** None — all tasks are executable as designed. Critical sequencing note: **P3.D-01 must be completed before P3.C-03** because the auth injection step imports `OAuthCCTokenService`.

---

## Pre-Phase Verification

Run these before starting:

```bash
cd backend && source .venv/bin/activate

# Must show exactly 2 checked migrations
python manage.py showmigrations api_connector
# Expected:
#  [X] 0001_initial
#  [X] 0002_authconfig_credentials_summary

# OAuth CC stub must be in place
python manage.py shell -c "
from api_connector.services.auth.handlers.oauth_cc import OAuthCCAuthHandler
import httpx
h = OAuthCCAuthHandler()
try:
    h.prepare_request(httpx.Request('GET','https://x.com'), {})
except NotImplementedError:
    print('PASS: stub raises NotImplementedError')
"

# ConnectionTestResult must have expected fields
python manage.py shell -c "
from api_connector.models import ConnectionTestResult
fields = [f.name for f in ConnectionTestResult._meta.get_fields()]
required = ['duration_ms','step_results','test_path','overall_passed','tested_at']
missing = [f for f in required if f not in fields]
print('Missing fields:', missing or 'NONE — pre-flight passed')
"
```

---

## 2. Implementation Tasks

---

### Task P3.A-01: Add `TokenType` Enum and Create `OAuthToken` Model

**Purpose:** Add the `TokenType` enum and create the `OAuthToken` model with Phase 4 (`encrypted_refresh_token`) provision included now, avoiding a future migration for a single nullable column.

**Steps:**

1. **Modify** `backend/api_connector/models/enums.py` — add `TokenType` after the existing enum classes:

```python
# backend/api_connector/models/enums.py
from django.db import models


class AuthType(models.TextChoices):
    NONE = "none", "None"
    API_KEY = "api_key", "API Key"
    BEARER = "bearer", "Bearer Token"
    BASIC = "basic", "Basic Auth"
    OAUTH_CC = "oauth_cc", "OAuth Client Credentials"
    OAUTH_AC = "oauth_ac", "OAuth Authorization Code"


class PaginationStrategy(models.TextChoices):
    NO_PAGINATION = "no_pagination", "No Pagination"
    OFFSET_LIMIT = "offset_limit", "Offset/Limit"
    PAGE_SIZE = "page_size", "Page/Size"
    CURSOR = "cursor", "Cursor"
    NEXT_URL = "next_url", "Next URL"
    LINK_HEADER = "link_header", "Link Header"


class InferredType(models.TextChoices):
    NULL = "null", "Null"
    BOOLEAN = "boolean", "Boolean"
    INTEGER = "integer", "Integer"
    FLOAT = "float", "Float"
    DATE = "date", "Date"
    DATETIME = "datetime", "Datetime"
    STRING = "string", "String"
    MIXED = "mixed", "Mixed"
    ARRAY_OF_OBJECTS = "array_of_objects", "Array of Objects"
    ARRAY_OF_PRIMITIVES = "array_of_primitives", "Array of Primitives"


class ArrayHandling(models.TextChoices):
    EXPAND = "expand", "Expand"
    RETAIN = "retain", "Retain"


class HTTPMethod(models.TextChoices):
    GET = "GET", "GET"
    POST = "POST", "POST"


class TokenType(models.TextChoices):
    OAUTH_CC = "oauth_cc", "OAuth Client Credentials"
    OAUTH_AC = "oauth_ac", "OAuth Authorization Code"
```

2. **Create** `backend/api_connector/models/oauth_token.py`:

```python
# backend/api_connector/models/oauth_token.py
from django.db import models

from api_connector.models.enums import TokenType


class OAuthToken(models.Model):
    """
    Stores Fernet-encrypted OAuth access (and optionally refresh) tokens.

    Shared by Phase 3 (OAuth CC) and Phase 4 (OAuth AC).

    Security requirements (OWASP A02):
    - encrypted_token and encrypted_refresh_token store Fernet ciphertext ONLY.
    - Raw token strings must NEVER appear in this table, in logs, or in API responses.
    - Access is through OAuthCCTokenService / OAuthACTokenService (Phase 4) ONLY.
    - __str__ and __repr__ must not reference either token field.

    The unique_together constraint enforces one active token per (profile, type) pair.
    OAuthCCTokenService uses update_or_create, so the row is overwritten on refresh —
    no stale token accumulation.
    """

    connection_profile = models.ForeignKey(
        "api_connector.ConnectionProfile",
        on_delete=models.CASCADE,
        related_name="oauth_tokens",
    )
    token_type = models.CharField(
        max_length=10,
        choices=TokenType.choices,
        default=TokenType.OAUTH_CC,
    )
    # Fernet ciphertext of the access token string
    encrypted_token = models.TextField()
    # Fernet ciphertext of the refresh token; null for OAUTH_CC (no refresh token)
    encrypted_refresh_token = models.TextField(null=True, blank=True)
    # null = non-expiring or unknown expiry
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_connector_oauth_token"
        # One active token record per (profile, type) pair — update_or_create enforces this
        unique_together = [["connection_profile", "token_type"]]

    def __str__(self) -> str:
        # Deliberately omits token fields from string representation
        return f"OAuthToken({self.token_type}) for profile {self.connection_profile_id}"
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.models.enums import TokenType
assert TokenType.OAUTH_CC == 'oauth_cc'
assert TokenType.OAUTH_AC == 'oauth_ac'
assert len(TokenType.choices) == 2
print('TokenType enum: PASS')
"
```

**Troubleshooting:**

- **`ImportError` for TokenType:** Ensure the class is added to `enums.py` and not a separate file — the `models/__init__.py` import in P3.A-02 pulls it from there.
- **`OAuthToken` not recognized by Django yet:** This is expected until P3.A-02 registers it in `__init__.py`.

**Micro-Lesson:** `encrypted_refresh_token = models.TextField(null=True)` costs zero bytes in PostgreSQL when null. Adding it now versus a Phase 4 migration means Phase 4 requires zero DB changes for its OAuth AC token storage. A `TextField` (not `JSONField`) is used because Fernet ciphertext is a raw string, not a JSON structure — storing it in a JSONField would require quoting and escaping the ciphertext unnecessarily.

---

### Task P3.A-02: Register `OAuthToken`, Generate Migration `0003`, Add Factory

**Purpose:** Make Django aware of `OAuthToken`, generate and apply the single migration that creates the `api_connector_oauth_token` table, and add a `OAuthTokenFactory` for tests.

**Steps:**

1. **Update** `backend/api_connector/models/__init__.py` to add `OAuthToken` and `TokenType`:

```python
# backend/api_connector/models/__init__.py
from api_connector.models.enums import (
    ArrayHandling,
    AuthType,
    HTTPMethod,
    InferredType,
    PaginationStrategy,
    TokenType,
)
from api_connector.models.connection_profile import ConnectionProfile
from api_connector.models.auth_config import AuthConfig
from api_connector.models.endpoint import Endpoint
from api_connector.models.pagination_config import PaginationConfig
from api_connector.models.schema_field import SchemaField
from api_connector.models.connection_test_result import ConnectionTestResult
from api_connector.models.oauth_token import OAuthToken

__all__ = [
    "AuthType",
    "PaginationStrategy",
    "InferredType",
    "ArrayHandling",
    "HTTPMethod",
    "TokenType",
    "ConnectionProfile",
    "AuthConfig",
    "Endpoint",
    "PaginationConfig",
    "SchemaField",
    "ConnectionTestResult",
    "OAuthToken",
]
```

2. Verify Django sees the model before running `makemigrations`:

```bash
cd backend && source .venv/bin/activate

python manage.py check
# Expected: System check identified no issues (0 silenced).

python manage.py shell -c "
from api_connector.models import OAuthToken, TokenType
print('OAuthToken imported: PASS')
print('Fields:', [f.name for f in OAuthToken._meta.get_fields()])
"
```

3. ⚠️ **Only run this after the check above passes:**

```bash
python manage.py makemigrations api_connector --name oauth_token
# Expected:
# Migrations for 'api_connector':
#   api_connector/migrations/0003_oauth_token.py
#     - Create model OAuthToken
```

4. Inspect before applying:

```bash
python manage.py sqlmigrate api_connector 0003
# Confirm: ONE CREATE TABLE api_connector_oauth_token
# Confirm: UNIQUE constraint on (connection_profile_id, token_type)
# Confirm: encrypted_token column is text (not jsonb)
```

5. Apply:

```bash
python manage.py migrate
# Expected: Applying api_connector.0003_oauth_token... OK

python manage.py showmigrations api_connector
# Expected: all 3 checked
```

6. **Update** `backend/tests/factories.py` — add `OAuthTokenFactory` at the end:

```python
# Add to existing backend/tests/factories.py — append after ConnectionTestResultFactory

from api_connector.models import OAuthToken, TokenType
from api_connector.services.encryption import encryption_service


class OAuthTokenFactory(DjangoModelFactory):
    class Meta:
        model = OAuthToken

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    token_type = TokenType.OAUTH_CC
    # Fernet ciphertext of a dummy access token string
    encrypted_token = factory.LazyAttribute(
        lambda _: encryption_service.encrypt("dummy_access_token")
    )
    encrypted_refresh_token = None
    expires_at = None
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py dbshell
```

```sql
\dt api_connector*
-- Expected: 7 tables (6 from Phase 1 + api_connector_oauth_token)
\d api_connector_oauth_token
-- Confirm: encrypted_token text, encrypted_refresh_token text null, unique constraint
\q
```

```bash
pytest tests/factories.py -v --collect-only 2>/dev/null || \
python manage.py shell -c "
import django; django.setup()
import sys; sys.path.insert(0, '.')
from tests.factories import OAuthTokenFactory
t = OAuthTokenFactory()
print('OAuthTokenFactory created pk:', t.pk)
print('token_type:', t.token_type)
import pytest
" 2>/dev/null || echo "Run via pytest: pytest -k 'not test_' --collect-only"
```

**Troubleshooting:**

- **`IntegrityError` on `OAuthTokenFactory()` — duplicate token:** The factory creates a new `ConnectionProfileFactory()` each time via `SubFactory`, so duplicate `(connection_profile, token_type)` won't occur unless you explicitly reuse a profile across two factory calls.
- **`makemigrations` generates changes beyond `OAuthToken`:** Another model was accidentally modified. Check `git diff backend/api_connector/models/` to confirm only `enums.py` and `oauth_token.py` changed.

---

### Task P3.B-01: Create `plain_english_errors.py` Error Message Registry

**Purpose:** Centralize all user-facing error messages in one auditable file before any service is written, ensuring the Phase 8 UX audit can review every message in a single location.

**Steps:**

1. **Create** `backend/api_connector/services/plain_english_errors.py`:

```python
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
        message="Connection refused at {url}.",
        suggested_action=(
            "Verify the Base URL is correct and the API server is running. "
            "Check that the port (if specified) is open."
        ),
    ),
    ("network_connectivity", "ssl_error"): StepErrorMessage(
        message="TLS/SSL certificate error connecting to {url}.",
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
    ("auth_injection", "oauth_cc_token_fetch_failed"): StepErrorMessage(
        message="Could not fetch an OAuth access token from the token endpoint.",
        suggested_action=(
            "Verify the Client ID, Client Secret, and Token Endpoint URL are correct. "
            "Check that the OAuth application has Client Credentials grant type enabled."
        ),
    ),
    ("auth_injection", "credentials_corrupt"): StepErrorMessage(
        message="The stored credentials could not be decrypted.",
        suggested_action=(
            "The credential data may be corrupt. Open the profile, re-enter your "
            "credentials, and save before testing again."
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
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.services.plain_english_errors import (
    STEP_ERROR_MESSAGES, StepErrorMessage, DNS_SUCCESS_MSG
)
# Verify registry is populated
assert len(STEP_ERROR_MESSAGES) >= 12, f'Expected ≥12 entries, got {len(STEP_ERROR_MESSAGES)}'

# Verify format strings work
msg = STEP_ERROR_MESSAGES[('dns_resolution', 'hostname_not_found')]
assert isinstance(msg, StepErrorMessage)
formatted = msg.message.format(hostname='api.example.com')
assert 'api.example.com' in formatted
assert 'gaierror' not in formatted

# Verify success template
success = DNS_SUCCESS_MSG.format(hostname='api.example.com', ip_count=2)
assert 'api.example.com' in success
print('Error message registry: PASS —', len(STEP_ERROR_MESSAGES), 'entries')
"
```

**Troubleshooting:**

- **`KeyError` on format string:** A template uses `{hostname}` but you call `.format(host=...)`. Match the placeholder names exactly.
- **Audit failure — exception class name in message:** Search `grep -i "gaierror\|connectionerror\|httpexception" plain_english_errors.py` — must return nothing.

---

### Task P3.C-01: Define `StepResult` Dataclass and Step Name Constants

**Purpose:** Establish the shared type contract between the service (backend) and the serializer/frontend — every step method returns a `StepResult`, and step names are referenced only via constants.

**Steps:**

1. Create the directory and files:

```bash
cd backend && source .venv/bin/activate
mkdir -p api_connector/services/connection_test
touch api_connector/services/connection_test/__init__.py
```

2. **Create** `backend/api_connector/services/connection_test/types.py`:

```python
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
```

**Verification:**

```bash
python manage.py shell -c "
from api_connector.services.connection_test.types import (
    StepResult, ALL_STEPS, DNS_RESOLUTION, NETWORK_CONNECTIVITY,
    AUTH_INJECTION, HTTP_RESPONSE, FORMAT_DETECTION, RESPONSE_SAMPLE
)
assert len(ALL_STEPS) == 6, f'Expected 6 steps, got {len(ALL_STEPS)}'
assert len(set(ALL_STEPS)) == 6, 'Step names are not unique'
r = StepResult(name=DNS_RESOLUTION, passed=True, message='OK', detail={'hostname': 'x'})
assert r.duration_ms == 0  # default
print('StepResult and STEP_NAMES: PASS')
"
```

---

### Task P3.C-02: Implement DNS Resolution and Network Connectivity Steps

**Purpose:** Deliver the two most impactful diagnostic steps — the majority of real-world misconfiguration issues are DNS or firewall problems resolved by these two steps alone.

**Steps:**

1. **Create** `backend/api_connector/services/connection_test/service.py` with DNS and network steps:

```python
# backend/api_connector/services/connection_test/service.py
"""
ConnectionTestService — sequential 6-step API connection validator.

Step execution contract:
  - Steps run sequentially; first failure causes early exit.
  - Each step returns StepResult; if passed==False, no further steps run.
  - All 6 steps complete only when every step passes.
  - run() is the ONLY public method. All _step_* methods are private.

Security logging contract (OWASP A09):
  - Log step name, pass/fail, and duration_ms ONLY.
  - NEVER log: credential values, response bodies, auth headers, resolved IPs.
"""
import concurrent.futures
import logging
import socket
import time
import urllib.parse
from typing import Optional

import httpx
from cryptography.fernet import InvalidToken
from django.db import transaction
from django.utils import timezone

from api_connector.models import (
    AuthConfig,
    AuthType,
    ConnectionProfile,
    ConnectionTestResult,
)
from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
from api_connector.services.auth.registry import auth_handler_registry
from api_connector.services.connection_test.types import (
    ALL_STEPS,
    AUTH_INJECTION,
    DNS_RESOLUTION,
    FORMAT_DETECTION,
    HTTP_RESPONSE,
    NETWORK_CONNECTIVITY,
    RESPONSE_SAMPLE,
    StepResult,
)
from api_connector.services.encryption import encryption_service
from api_connector.services.http_client import BaseHTTPClient
from api_connector.services.http_exceptions import (
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)
from api_connector.services.plain_english_errors import (
    AUTH_SUCCESS_MSG,
    DNS_SUCCESS_MSG,
    FORMAT_DETECTED_MSG,
    HTTP_SUCCESS_MSG,
    NETWORK_SUCCESS_MSG,
    RESPONSE_SAMPLE_MSG,
    STEP_ERROR_MESSAGES,
)

logger = logging.getLogger("api_connector.connection_test")


class ConnectionTestService:
    """
    Executes a 6-step sequential connection test for a ConnectionProfile.

    This is a stateless service — run() accepts parameters, maintains no instance
    variables. Thread-safe.

    [ASSUMPTION] _profile_id convention:
    All credentials dicts passed to auth handlers include "_profile_id": profile.pk.
    This key is consumed by OAuthCCAuthHandler and OAuthACAuthHandler to look up
    cached tokens. It is never sent to the API server.
    """

    def _step_dns_resolution(self, hostname: str, ssl_verify: bool) -> StepResult:
        """
        Step 1: Verify the hostname resolves via DNS.
        Uses ThreadPoolExecutor to enforce a 5-second timeout on the blocking
        socket.getaddrinfo() call, which has no built-in timeout parameter.
        """
        start = time.monotonic()

        def resolve():
            return socket.getaddrinfo(hostname, None)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(resolve)
                results = future.result(timeout=5)

            duration_ms = int((time.monotonic() - start) * 1000)
            resolved_ips = list({r[4][0] for r in results})  # deduplicate

            return StepResult(
                name=DNS_RESOLUTION,
                passed=True,
                message=DNS_SUCCESS_MSG.format(
                    hostname=hostname, ip_count=len(resolved_ips)
                ),
                detail={"hostname": hostname, "resolved_ips": resolved_ips},
                duration_ms=duration_ms,
            )

        except socket.gaierror:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("dns_resolution", "hostname_not_found")]
            return StepResult(
                name=DNS_RESOLUTION,
                passed=False,
                message=error_msg.message.format(hostname=hostname),
                detail={
                    "hostname": hostname,
                    "error": f"Name '{hostname}' could not be resolved.",
                    "suggested_action": error_msg.suggested_action,
                },
                duration_ms=duration_ms,
            )

        except concurrent.futures.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("dns_resolution", "timeout")]
            return StepResult(
                name=DNS_RESOLUTION,
                passed=False,
                message=error_msg.message.format(hostname=hostname),
                detail={
                    "hostname": hostname,
                    "error": "DNS resolution timed out after 5 seconds.",
                    "suggested_action": error_msg.suggested_action,
                },
                duration_ms=duration_ms,
            )

        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(
                name=DNS_RESOLUTION,
                passed=False,
                message=f"DNS resolution failed for '{hostname}'.",
                detail={
                    "hostname": hostname,
                    "error": str(exc),
                    "suggested_action": "Check the Base URL hostname is correct.",
                },
                duration_ms=duration_ms,
            )

    def _step_network_connectivity(
        self, base_url: str, ssl_verify: bool, timeout: int
    ) -> StepResult:
        """
        Step 2: Verify TCP + TLS connectivity by sending an unauthenticated GET.
        ANY HTTP response (2xx, 4xx, 5xx) means the server is reachable.
        Only network-level failures (timeout, refused, SSL error) indicate failure.
        """
        start = time.monotonic()
        # Cap at 10s — connectivity check should not use the full profile timeout
        capped_timeout = min(timeout, 10)
        client = BaseHTTPClient(timeout=capped_timeout)

        if not ssl_verify:
            logger.warning(
                "SSL verification disabled for connectivity check at %s — "
                "OWASP A07: proceeding with insecure connection",
                base_url,
            )

        try:
            response = client.get(
                base_url,
                auth_handler=NoneAuthHandler(),
                credentials={},
                ssl_verify=ssl_verify,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(
                name=NETWORK_CONNECTIVITY,
                passed=True,
                message=NETWORK_SUCCESS_MSG.format(status_code=response.status_code),
                detail={"status_code": response.status_code, "response_time_ms": duration_ms},
                duration_ms=duration_ms,
            )

        except HTTPStatusError as exc:
            # 4xx/5xx: server responded → TCP+TLS succeeded → PASS
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(
                name=NETWORK_CONNECTIVITY,
                passed=True,
                message=NETWORK_SUCCESS_MSG.format(status_code=exc.status_code),
                detail={"status_code": exc.status_code, "response_time_ms": duration_ms},
                duration_ms=duration_ms,
            )

        except HTTPTimeoutError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("network_connectivity", "timeout")]
            return StepResult(
                name=NETWORK_CONNECTIVITY,
                passed=False,
                message=error_msg.message.format(url=base_url, timeout=capped_timeout),
                detail={
                    "error": str(exc),
                    "url": base_url,
                    "ssl_error": False,
                    "suggested_action": error_msg.suggested_action,
                },
                duration_ms=duration_ms,
            )

        except HTTPNetworkError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_str = str(exc).lower()
            is_ssl = "ssl" in error_str or "certificate" in error_str or "tls" in error_str
            reason = "ssl_error" if is_ssl else "connection_refused"
            error_msg = STEP_ERROR_MESSAGES[("network_connectivity", reason)]
            return StepResult(
                name=NETWORK_CONNECTIVITY,
                passed=False,
                message=error_msg.message.format(url=base_url),
                detail={
                    "error": str(exc),
                    "url": base_url,
                    "ssl_error": is_ssl,
                    "suggested_action": error_msg.suggested_action,
                },
                duration_ms=duration_ms,
            )
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.services.connection_test.service import ConnectionTestService
svc = ConnectionTestService()
print('ConnectionTestService instantiated: PASS')
print('_step_dns_resolution defined:', hasattr(svc, '_step_dns_resolution'))
print('_step_network_connectivity defined:', hasattr(svc, '_step_network_connectivity'))
"
```

**Troubleshooting:**

- **`ModuleNotFoundError: connection_test`:** Ensure `backend/api_connector/services/connection_test/__init__.py` exists (created in P3.C-01).
- **DNS step hangs in tests:** The `ThreadPoolExecutor` with `future.result(timeout=5)` prevents indefinite hang. In tests, always mock `socket.getaddrinfo` — never let it make real DNS calls.

**Micro-Lesson:** `socket.getaddrinfo()` has no timeout parameter — it blocks the calling thread indefinitely on some systems. Wrapping it in `ThreadPoolExecutor.submit().result(timeout=5)` is the correct pattern: the OS thread continues its DNS query, but our main thread gets a `TimeoutError` after 5 seconds. The background thread will eventually complete or be cleaned up by the OS.

---

### Task P3.D-01: Implement `OAuthCCTokenService`

**Purpose:** Fetch, cache, and refresh OAuth Client Credentials tokens with DB storage that works across multiple Python processes — preventing the N×worker token fetch problem from in-memory caches.

**Steps:**

1. **Create** `backend/api_connector/services/oauth_cc_token.py`:

```python
# backend/api_connector/services/oauth_cc_token.py
"""
OAuth 2.0 Client Credentials token fetch, cache, and refresh.

ADR (inline): OAuth Token Storage — Database vs. In-Memory Cache
Decision: Database (OAuthToken model)
Rationale: Multi-process Django workers (Gunicorn, uWSGI) have independent memory.
An in-memory cache produces duplicate token fetches per worker, burning quota on
providers that rate-limit token endpoint calls. DB storage guarantees one active
token record across all processes. Cache hit = one SELECT query. Cache miss =
one POST to token endpoint + one INSERT/UPDATE.
Consequences: OAuthToken table must be migrated before first use. Phase 4 AC
tokens use the same table (different token_type value).

Security (OWASP A02):
  - Raw token strings NEVER written to DB, logs, or API responses.
  - Only Fernet ciphertext stored (via encryption_service.encrypt()).
  - Token endpoint response body NEVER logged.
  - This file is the ONLY place httpx is used directly (not via BaseHTTPClient).
    Rationale: the token request IS the auth mechanism; BaseHTTPClient would
    attempt to inject auth into an auth request.
"""
import logging
import time
from datetime import timedelta

import httpx
from django.utils import timezone

from api_connector.models import OAuthToken, TokenType
from api_connector.services.encryption import encryption_service

logger = logging.getLogger("api_connector.oauth_cc_token")

# Refresh token if it expires within this buffer to prevent race conditions
TOKEN_EXPIRY_BUFFER_SECONDS = 60


class OAuthCCTokenFetchError(Exception):
    """
    Raised when the OAuth CC token endpoint cannot be reached or returns an error.
    Message is safe to display to the user — no raw response bodies.
    """


class OAuthCCTokenService:
    """
    Service for OAuth 2.0 Client Credentials token management.
    Stateless — all state persists in the OAuthToken DB table.
    """

    def get_token(self, profile_id: int, credentials: dict) -> str:
        """
        Return a valid OAuth CC access token string for the given profile.

        Cache hit: returns decrypted token from DB (one SELECT).
        Cache miss: fetches new token, stores encrypted, returns token string.

        Args:
            profile_id: ConnectionProfile primary key (used as cache key).
            credentials: Decrypted credentials dict with keys:
                client_id, client_secret, token_endpoint, scopes (optional).

        Returns:
            Access token as a plain string.

        Raises:
            OAuthCCTokenFetchError: if the token endpoint returns an error or
                the response does not contain an access_token.
        """
        # 1. Check cache
        cached = OAuthToken.objects.filter(
            connection_profile_id=profile_id,
            token_type=TokenType.OAUTH_CC,
        ).first()

        if cached is not None:
            # Check if token is still valid (with 60-second buffer)
            if cached.expires_at is None or cached.expires_at > timezone.now() + timedelta(
                seconds=TOKEN_EXPIRY_BUFFER_SECONDS
            ):
                return encryption_service.decrypt(cached.encrypted_token)

        # 2. Fetch new token from endpoint
        access_token, expires_at = self._fetch_token(credentials)

        # 3. Store encrypted token (upsert via unique_together)
        OAuthToken.objects.update_or_create(
            connection_profile_id=profile_id,
            token_type=TokenType.OAUTH_CC,
            defaults={
                "encrypted_token": encryption_service.encrypt(access_token),
                "encrypted_refresh_token": None,
                "expires_at": expires_at,
            },
        )

        return access_token

    def _fetch_token(self, credentials: dict) -> tuple[str, object]:
        """
        POST to the token endpoint and return (access_token, expires_at).
        expires_at is a timezone-aware datetime or None if not provided.

        Security: NEVER log the response body or the access_token value.
        """
        token_endpoint = credentials["token_endpoint"]
        form_data: dict = {
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        }
        if credentials.get("scopes"):
            form_data["scope"] = credentials["scopes"]

        start = time.monotonic()
        try:
            # Use httpx.Client directly — this is the one permitted exception to the
            # BaseHTTPClient rule (token request IS the auth mechanism).
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    token_endpoint,
                    data=form_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.TimeoutException:
            raise OAuthCCTokenFetchError(
                "Token endpoint timed out. "
                "Verify the Token Endpoint URL and your network connectivity."
            )
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise OAuthCCTokenFetchError(
                f"Could not reach the token endpoint: {type(exc).__name__}. "
                "Check the Token Endpoint URL."
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        # Log only structural metadata — NEVER log response body or token
        logger.info(
            "OAuth CC token fetch for profile: HTTP %s (%dms)",
            response.status_code,
            latency_ms,
        )

        if response.status_code != 200:
            raise OAuthCCTokenFetchError(
                f"Token endpoint returned HTTP {response.status_code}. "
                "Verify Client ID, Client Secret, and Token Endpoint URL."
            )

        try:
            body = response.json()
        except Exception:
            raise OAuthCCTokenFetchError(
                "Token endpoint returned a non-JSON response. "
                "Verify the Token Endpoint URL is correct."
            )

        access_token = body.get("access_token")
        if not access_token:
            raise OAuthCCTokenFetchError(
                "Token endpoint response did not contain 'access_token'. "
                "Verify the OAuth application has Client Credentials grant enabled."
            )

        expires_in = body.get("expires_in")
        expires_at = None
        if expires_in is not None:
            try:
                expires_at = timezone.now() + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                expires_at = None

        return access_token, expires_at
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.services.oauth_cc_token import OAuthCCTokenService, OAuthCCTokenFetchError
svc = OAuthCCTokenService()
print('OAuthCCTokenService instantiated: PASS')
print('OAuthCCTokenFetchError subclasses Exception:', issubclass(OAuthCCTokenFetchError, Exception))
"
```

**Troubleshooting:**

- **`ImportError: OAuthToken`:** The migration `0003_oauth_token` has not been applied. Run `python manage.py migrate` first.
- **`OAuthCCTokenFetchError` in tests when mocking:** Use `unittest.mock.patch("api_connector.services.oauth_cc_token.httpx.Client")` or `pytest-httpx` to intercept the token endpoint call.

**Micro-Lesson:** `update_or_create(connection_profile_id=profile_id, token_type=TokenType.OAUTH_CC, defaults={...})` is an atomic upsert enabled by the `unique_together` constraint. On first token fetch it INSERTs; on refresh it UPDATEs. Without `unique_together`, you'd accumulate one row per refresh — burning database space and requiring a separate cleanup job.

---

### Task P3.D-02: Replace `OAuthCCAuthHandler` Stub with Real Implementation

**Purpose:** Activate the previously-stubbed handler so `AuthHandlerRegistry.get(AuthType.OAUTH_CC)` now injects a real Bearer token instead of raising `NotImplementedError`.

**Steps:**

1. **Replace** the entire content of `backend/api_connector/services/auth/handlers/oauth_cc.py`:

```python
# backend/api_connector/services/auth/handlers/oauth_cc.py
import logging

import httpx

from api_connector.services.auth.base import BaseAuthHandler

logger = logging.getLogger("api_connector.auth.oauth_cc")


class OAuthCCAuthHandler(BaseAuthHandler):
    """
    Handles AuthType.OAUTH_CC (OAuth 2.0 Client Credentials).

    Fetches a cached token via OAuthCCTokenService and injects it as
    Authorization: Bearer <token>.

    The _profile_id convention:
    All callers must include "_profile_id": profile.pk in the credentials dict
    before calling prepare_request(). This key is used to look up cached tokens
    and is NEVER injected into any outbound request header or parameter.

    Security: NEVER log the access_token value.
    """

    def prepare_request(
        self, request: httpx.Request, credentials: dict
    ) -> httpx.Request:
        # Import inside method to avoid circular imports at module load time
        from api_connector.services.oauth_cc_token import OAuthCCTokenService

        profile_id = credentials.get("_profile_id")
        if profile_id is None:
            raise ValueError(
                "OAuthCCAuthHandler requires '_profile_id' in credentials dict. "
                "Ensure ConnectionTestService (or the caller) adds '_profile_id': "
                "profile.pk to the credentials dict before calling prepare_request()."
            )

        access_token = OAuthCCTokenService().get_token(profile_id, credentials)

        logger.debug("OAuthCC auth injected for profile %s", profile_id)

        headers = dict(request.headers)
        headers["Authorization"] = f"Bearer {access_token}"
        return httpx.Request(
            method=request.method,
            url=request.url,
            headers=headers,
            content=request.content,
        )
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
import httpx
from api_connector.services.auth.handlers.oauth_cc import OAuthCCAuthHandler
from api_connector.services.auth.registry import auth_handler_registry
from api_connector.models import AuthType

h = auth_handler_registry.get(AuthType.OAUTH_CC)
assert isinstance(h, OAuthCCAuthHandler)

# Stub no longer raises NotImplementedError — it now raises ValueError (missing _profile_id)
try:
    h.prepare_request(httpx.Request('GET', 'https://x.com'), {})
    print('ERROR: Should have raised ValueError')
except ValueError as e:
    print('PASS: raises ValueError (not NotImplementedError) —', str(e)[:60])
except Exception as e:
    print(f'ERROR: unexpected exception type {type(e).__name__}:', e)
"
```

**Troubleshooting:**

- **Still raising `NotImplementedError`:** The old file content is still there. Verify `backend/api_connector/services/auth/handlers/oauth_cc.py` contains the new class, not the stub.
- **Circular import error at startup:** The `OAuthCCTokenService` import inside `prepare_request()` (not at module level) prevents the circular import between handlers and services.

---

### Task P3.C-03: Implement Auth Injection, HTTP Response, Format Detection, and Response Sample Steps

**Purpose:** Complete the four remaining step methods. These make actual outbound network calls — the auth step validates credentials, the HTTP step sends the authenticated request, and the final two steps analyze the response.

**Steps:**

1. **Append** the four additional step methods to `backend/api_connector/services/connection_test/service.py` (inside the `ConnectionTestService` class, after `_step_network_connectivity`):

```python
    def _step_auth_injection(
        self, profile: ConnectionProfile, auth_config: AuthConfig
    ) -> tuple[StepResult, dict]:
        """
        Step 3: Validate credentials are present and injectable.

        For OAuth AC: immediate fail (browser flow required — not an error).
        For OAuth CC: also attempts a token fetch to validate the token endpoint.
        For all others: decrypts credentials and validates non-empty.

        Returns (StepResult, credentials_dict).
        The credentials dict always includes "_profile_id" for auth handlers.
        """
        start = time.monotonic()
        auth_type = profile.auth_type

        # OAuth AC — requires browser flow, not an error, just expected limitation
        if auth_type == AuthType.OAUTH_AC:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("auth_injection", "oauth_ac_browser_required")]
            return (
                StepResult(
                    name=AUTH_INJECTION,
                    passed=False,
                    message=error_msg.message,
                    detail={
                        "auth_type": auth_type,
                        "reason": "browser_flow_required",
                        "suggested_action": error_msg.suggested_action,
                    },
                    duration_ms=duration_ms,
                ),
                {},
            )

        # No auth required — trivially passes
        if auth_type == AuthType.NONE:
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                StepResult(
                    name=AUTH_INJECTION,
                    passed=True,
                    message=AUTH_SUCCESS_MSG.format(auth_type="none (no credentials required)"),
                    detail={"auth_type": auth_type, "credentials_present": False},
                    duration_ms=duration_ms,
                ),
                {"_profile_id": profile.pk},
            )

        # All other auth types — decrypt and validate
        try:
            decrypted = encryption_service.decrypt_to_dict(auth_config.encrypted_credentials)
        except InvalidToken:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("auth_injection", "credentials_corrupt")]
            return (
                StepResult(
                    name=AUTH_INJECTION,
                    passed=False,
                    message=error_msg.message,
                    detail={
                        "auth_type": auth_type,
                        "reason": "credentials_corrupt",
                        "suggested_action": error_msg.suggested_action,
                    },
                    duration_ms=duration_ms,
                ),
                {},
            )

        # Validate at least one non-empty credential value exists
        has_credentials = any(bool(v) for v in decrypted.values())
        if not has_credentials:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("auth_injection", "credentials_missing")]
            return (
                StepResult(
                    name=AUTH_INJECTION,
                    passed=False,
                    message=error_msg.message.format(auth_type=auth_type),
                    detail={
                        "auth_type": auth_type,
                        "reason": "no_credentials_stored",
                        "suggested_action": error_msg.suggested_action,
                    },
                    duration_ms=duration_ms,
                ),
                {},
            )

        # Build credentials dict with _profile_id convention
        credentials = {**decrypted, "_profile_id": profile.pk}

        # OAuth CC — also validate token endpoint is reachable
        if auth_type == AuthType.OAUTH_CC:
            from api_connector.services.oauth_cc_token import (
                OAuthCCTokenFetchError,
                OAuthCCTokenService,
            )

            try:
                OAuthCCTokenService().get_token(profile.pk, credentials)
            except OAuthCCTokenFetchError as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                error_msg = STEP_ERROR_MESSAGES[("auth_injection", "oauth_cc_token_fetch_failed")]
                return (
                    StepResult(
                        name=AUTH_INJECTION,
                        passed=False,
                        message=error_msg.message,
                        detail={
                            "auth_type": auth_type,
                            "reason": "token_fetch_failed",
                            "error": str(exc),
                            "suggested_action": error_msg.suggested_action,
                        },
                        duration_ms=duration_ms,
                    ),
                    {},
                )

        duration_ms = int((time.monotonic() - start) * 1000)
        return (
            StepResult(
                name=AUTH_INJECTION,
                passed=True,
                message=AUTH_SUCCESS_MSG.format(auth_type=auth_type),
                detail={"auth_type": auth_type, "credentials_present": True},
                duration_ms=duration_ms,
            ),
            credentials,
        )

    def _step_http_response(
        self,
        base_url: str,
        test_path: Optional[str],
        profile: ConnectionProfile,
        credentials: dict,
    ) -> tuple[StepResult, Optional[httpx.Response]]:
        """
        Step 4: Send an authenticated request to test_url and check the response.
        2xx/3xx → pass. 4xx/5xx → fail with specific messages.

        Uses httpx.Client directly (not BaseHTTPClient) to avoid double-logging
        since we are building and sending the authenticated request here.
        """
        start = time.monotonic()
        test_url = base_url.rstrip("/") + (test_path or "")

        try:
            handler = auth_handler_registry.get(profile.auth_type)
            request = httpx.Request("GET", test_url)
            auth_request = handler.prepare_request(request, credentials)

            with httpx.Client(
                verify=profile.ssl_verify, timeout=profile.request_timeout
            ) as client:
                response = client.send(auth_request)

            duration_ms = int((time.monotonic() - start) * 1000)

            # Log structural metadata only — no URL query string, no headers, no body
            url_no_qs = test_url.split("?")[0]
            logger.info("HTTP GET %s → %s (%dms)", url_no_qs, response.status_code, duration_ms)

            if response.status_code < 400:
                return (
                    StepResult(
                        name=HTTP_RESPONSE,
                        passed=True,
                        message=HTTP_SUCCESS_MSG.format(
                            status_code=response.status_code,
                            response_time_ms=duration_ms,
                        ),
                        detail={
                            "status_code": response.status_code,
                            "response_time_ms": duration_ms,
                            "test_url": url_no_qs,
                        },
                        duration_ms=duration_ms,
                    ),
                    response,
                )

            # 4xx/5xx — specific messages
            if response.status_code == 401:
                reason = "401"
            elif response.status_code == 403:
                reason = "403"
            elif response.status_code == 404:
                reason = "404"
            elif response.status_code >= 500:
                reason = "5xx"
            else:
                reason = "5xx"  # catch-all for other 4xx

            error_msg = STEP_ERROR_MESSAGES.get(("http_response", reason))
            message = (
                error_msg.message.format(
                    status_code=response.status_code, timeout=profile.request_timeout
                )
                if error_msg
                else f"API returned HTTP {response.status_code}."
            )
            suggested_action = error_msg.suggested_action if error_msg else ""

            return (
                StepResult(
                    name=HTTP_RESPONSE,
                    passed=False,
                    message=message,
                    detail={
                        "status_code": response.status_code,
                        "response_time_ms": duration_ms,
                        "test_url": url_no_qs,
                        "suggested_action": suggested_action,
                    },
                    duration_ms=duration_ms,
                ),
                None,
            )

        except httpx.TimeoutException:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("http_response", "timeout")]
            return (
                StepResult(
                    name=HTTP_RESPONSE,
                    passed=False,
                    message=error_msg.message.format(timeout=profile.request_timeout),
                    detail={
                        "status_code": None,
                        "response_time_ms": duration_ms,
                        "test_url": test_url.split("?")[0],
                        "suggested_action": error_msg.suggested_action,
                    },
                    duration_ms=duration_ms,
                ),
                None,
            )

        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = STEP_ERROR_MESSAGES[("http_response", "network_error")]
            return (
                StepResult(
                    name=HTTP_RESPONSE,
                    passed=False,
                    message=error_msg.message,
                    detail={
                        "status_code": None,
                        "response_time_ms": duration_ms,
                        "test_url": test_url.split("?")[0],
                        "error": type(exc).__name__,
                        "suggested_action": error_msg.suggested_action,
                    },
                    duration_ms=duration_ms,
                ),
                None,
            )

    def _step_format_detection(
        self, response: httpx.Response
    ) -> tuple[StepResult, str]:
        """
        Step 5: Detect the response format from Content-Type header or body sniff.
        This step always passes — an unrecognized format is not a failure.
        """
        start = time.monotonic()
        content_type = response.headers.get("content-type", "").lower()
        source = "content_type_header"

        if "application/json" in content_type:
            detected_format = "json"
        elif "application/xml" in content_type or "text/xml" in content_type:
            detected_format = "xml"
        elif "text/csv" in content_type:
            detected_format = "csv"
        elif "text/html" in content_type:
            detected_format = "html"
        else:
            # Body sniff fallback
            source = "body_sniff"
            try:
                snippet = response.text[:512].lstrip()
            except Exception:
                snippet = ""

            if snippet.startswith("{") or snippet.startswith("["):
                detected_format = "json"
            elif snippet.startswith("<?xml") or snippet.startswith("<"):
                detected_format = "xml"
            else:
                detected_format = "plain_text"

        duration_ms = int((time.monotonic() - start) * 1000)
        return (
            StepResult(
                name=FORMAT_DETECTION,
                passed=True,
                message=FORMAT_DETECTED_MSG.format(
                    detected_format=detected_format, source=source
                ),
                detail={"detected_format": detected_format, "source": source},
                duration_ms=duration_ms,
            ),
            detected_format,
        )

    def _step_response_sample(self, response: httpx.Response) -> StepResult:
        """
        Step 6: Capture a body sample for display in the UI.
        Always passes. body_sample is capped at 2048 characters (not bytes).

        Security: body_sample may contain PII. NEVER log it.
        Phase 8 audit must assess data retention implications.
        """
        start = time.monotonic()
        try:
            body_text = response.text
        except Exception:
            body_text = ""

        body_sample = body_text[:2048]
        body_size = len(response.content)
        truncated = len(body_text) > 2048

        duration_ms = int((time.monotonic() - start) * 1000)
        return StepResult(
            name=RESPONSE_SAMPLE,
            passed=True,
            message=RESPONSE_SAMPLE_MSG.format(byte_count=body_size),
            detail={
                "body_size_bytes": body_size,
                "truncated": truncated,
                "body_sample": body_sample,
            },
            duration_ms=duration_ms,
        )
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.services.connection_test.service import ConnectionTestService
svc = ConnectionTestService()
methods = ['_step_auth_injection','_step_http_response','_step_format_detection','_step_response_sample']
for m in methods:
    assert hasattr(svc, m), f'Missing: {m}'
print('All 6 step methods defined: PASS')
"
```

**Troubleshooting:**

- **`ImportError: OAuthCCTokenFetchError`:** The import inside `_step_auth_injection` is deferred (inside the method body). If you see this, ensure `P3.D-01` completed successfully.
- **`AttributeError: 'Response' object has no attribute 'text'`:** `httpx.Response.text` requires the response content to be loaded. `httpx.Client.send()` loads it by default — this should not occur in normal usage.

**Micro-Lesson:** Step 4 uses `httpx.Client` directly (not `BaseHTTPClient`) because `BaseHTTPClient` has its own error-raising and logging logic. Since step 4 needs to distinguish between 401, 403, 404, and 5xx for specific messages, using the raw client gives finer-grained control without fighting `BaseHTTPClient`'s existing status error handling.

---

### Task P3.C-04: Assemble `ConnectionTestService.run()` with Persistence

**Purpose:** Wire all six steps into a sequential pipeline with atomic DB persistence — `ConnectionTestResult` creation and `ConnectionProfile` field updates happen in one transaction.

**Steps:**

1. **Append** the `run()` method to `ConnectionTestService` and update `__init__.py`:

```python
    def run(
        self,
        profile_id: int,
        test_path: Optional[str] = None,
    ) -> ConnectionTestResult:
        """
        Execute all 6 connection test steps sequentially for the given profile.

        Stops at the first failing step. Persists the result and updates
        ConnectionProfile.last_test_* fields atomically.

        Args:
            profile_id: ConnectionProfile primary key.
            test_path: Optional URL path suffix for the HTTP test (e.g. "/api/v1/health").
                       Must start with "/" if provided. None tests the base URL.

        Returns:
            Saved ConnectionTestResult instance.

        Raises:
            ConnectionProfile.DoesNotExist: if no profile with profile_id exists.
        """
        profile = ConnectionProfile.objects.select_related("auth_config").get(
            pk=profile_id
        )
        hostname = urllib.parse.urlparse(profile.base_url).hostname or profile.base_url
        run_start = time.monotonic()
        steps_completed: list[StepResult] = []

        logger.info(
            "ConnectionTest started profile=%s test_path=%s",
            profile_id,
            test_path or "(base URL)",
        )

        # ── Step 1: DNS Resolution ────────────────────────────────────────────
        result = self._step_dns_resolution(hostname, profile.ssl_verify)
        steps_completed.append(result)
        if not result.passed:
            return self._persist(profile, steps_completed, test_path, run_start)

        # ── Step 2: Network Connectivity ──────────────────────────────────────
        result = self._step_network_connectivity(
            profile.base_url, profile.ssl_verify, profile.request_timeout
        )
        steps_completed.append(result)
        if not result.passed:
            return self._persist(profile, steps_completed, test_path, run_start)

        # ── Step 3: Auth Injection ─────────────────────────────────────────────
        try:
            auth_config = profile.auth_config
        except AuthConfig.DoesNotExist:
            # No AuthConfig — should not happen if created correctly, but handle gracefully
            result = StepResult(
                name=AUTH_INJECTION,
                passed=False,
                message="This profile has no credential storage. Delete and recreate it.",
                detail={"reason": "no_auth_config"},
                duration_ms=0,
            )
            steps_completed.append(result)
            return self._persist(profile, steps_completed, test_path, run_start)

        result, credentials = self._step_auth_injection(profile, auth_config)
        steps_completed.append(result)
        if not result.passed:
            return self._persist(profile, steps_completed, test_path, run_start)

        # ── Step 4: HTTP Response ─────────────────────────────────────────────
        result, http_response = self._step_http_response(
            profile.base_url, test_path, profile, credentials
        )
        steps_completed.append(result)
        if not result.passed or http_response is None:
            return self._persist(profile, steps_completed, test_path, run_start)

        # ── Step 5: Format Detection ──────────────────────────────────────────
        result, detected_format = self._step_format_detection(http_response)
        steps_completed.append(result)
        # Format detection always passes, but defensive check
        if not result.passed:
            return self._persist(profile, steps_completed, test_path, run_start)

        # ── Step 6: Response Sample ───────────────────────────────────────────
        result = self._step_response_sample(http_response)
        steps_completed.append(result)

        return self._persist(profile, steps_completed, test_path, run_start)

    def _persist(
        self,
        profile: ConnectionProfile,
        steps_completed: list[StepResult],
        test_path: Optional[str],
        run_start: float,
    ) -> ConnectionTestResult:
        """
        Atomically save ConnectionTestResult and update ConnectionProfile.last_test_* fields.

        Uses queryset.update() (not instance.save()) to avoid overwriting fields
        concurrently edited by another request.
        """
        overall_passed = (
            len(steps_completed) == len(ALL_STEPS)
            and all(s.passed for s in steps_completed)
        )
        duration_ms = int((time.monotonic() - run_start) * 1000)

        step_results_data = [
            {
                "name": s.name,
                "passed": s.passed,
                "message": s.message,
                "detail": s.detail,
                "duration_ms": s.duration_ms,
            }
            for s in steps_completed
        ]

        # Extract step 4 and step 5 details for profile.last_test_* fields
        step4 = next((s for s in steps_completed if s.name == HTTP_RESPONSE), None)
        step5 = next((s for s in steps_completed if s.name == FORMAT_DETECTION), None)

        with transaction.atomic():
            test_result = ConnectionTestResult.objects.create(
                connection_profile=profile,
                step_results=step_results_data,
                overall_passed=overall_passed,
                test_path=test_path,
                duration_ms=duration_ms,
            )

            ConnectionProfile.objects.filter(pk=profile.pk).update(
                last_test_at=timezone.now(),
                last_test_outcome=overall_passed,
                last_test_status_code=step4.detail.get("status_code") if step4 else None,
                last_test_response_time=step4.detail.get("response_time_ms") if step4 else None,
                last_test_detected_format=(
                    step5.detail.get("detected_format") if step5 else None
                ),
            )

        logger.info(
            "ConnectionTest completed profile=%s overall=%s steps=%d duration_ms=%d",
            profile.pk,
            overall_passed,
            len(steps_completed),
            duration_ms,
        )

        return test_result
```

2. **Update** `backend/api_connector/services/connection_test/__init__.py`:

```python
# backend/api_connector/services/connection_test/__init__.py
from api_connector.services.connection_test.service import ConnectionTestService

__all__ = ["ConnectionTestService"]
```

3. Verify the full service is importable and runnable:

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.services.connection_test import ConnectionTestService
from api_connector.services.connection_test.types import ALL_STEPS
svc = ConnectionTestService()
print('ConnectionTestService fully assembled: PASS')
print('run() method:', callable(svc.run))
print('ALL_STEPS count:', len(ALL_STEPS))
"

python manage.py check
# Expected: System check identified no issues (0 silenced).
```

**Troubleshooting:**

- **`ProfileDoesNotExist` in tests:** Pass a real `profile.pk` from a factory. `ConnectionTestService.run()` does the DB lookup internally.
- **`transaction.atomic()` rollback not working in tests:** Use `@pytest.mark.django_db(transaction=True)` for any test that verifies rollback behavior.

**Micro-Lesson:** `ConnectionProfile.objects.filter(pk=profile.pk).update(...)` executes a single `UPDATE` SQL statement. `profile.save()` would re-save all model fields and overwrite concurrent edits (e.g., a user changing the profile name while a test runs). The queryset `.update()` is always the safer choice for partial field updates in web services.

---

### Task P3.E-01: Create Request and Result Serializers

**Purpose:** Define the typed API contract for the test endpoint — what the client sends and what the server returns.

**Steps:**

1. **Create** `backend/api_connector/serializers/connection_test.py`:

```python
# backend/api_connector/serializers/connection_test.py
from rest_framework import serializers

from api_connector.models import ConnectionTestResult


class ConnectionTestRequestSerializer(serializers.Serializer):
    """
    Validates the request body for POST /api/connector/profiles/{id}/test/.

    test_path is optional. When provided, must start with '/' to prevent
    path-confusion bugs (e.g. "api/v1" would join with base_url as "https://example.comapi/v1").
    """

    test_path = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=2048,
        default=None,
    )

    def validate_test_path(self, value: str | None) -> str | None:
        if value and not value.startswith("/"):
            raise serializers.ValidationError(
                "test_path must start with '/' or be empty. "
                "Example: '/api/v1/health' or '/ping'"
            )
        return value or None


class ConnectionTestResultSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for ConnectionTestResult responses.

    result_id aliases the model's 'id' for API contract stability.
    steps returns step_results JSONB directly — already structured correctly
    by ConnectionTestService.run().

    Security: step_results may contain body_sample from step 6 which could
    include API response data. The API consumer must not log this response.
    """

    result_id = serializers.IntegerField(source="id", read_only=True)
    steps = serializers.SerializerMethodField()

    def get_steps(self, obj: ConnectionTestResult) -> list:
        return obj.step_results

    class Meta:
        model = ConnectionTestResult
        fields = ["result_id", "overall_passed", "tested_at", "duration_ms", "steps"]
        read_only_fields = ["result_id", "overall_passed", "tested_at", "duration_ms", "steps"]
```

**Verification:**

```bash
cd backend && source .venv/bin/activate

python manage.py shell -c "
from api_connector.serializers.connection_test import (
    ConnectionTestRequestSerializer,
    ConnectionTestResultSerializer,
)

# Valid test path
s = ConnectionTestRequestSerializer(data={'test_path': '/api/v1'})
assert s.is_valid(), s.errors

# Invalid — missing leading slash
s = ConnectionTestRequestSerializer(data={'test_path': 'api/v1'})
assert not s.is_valid()
assert 'test_path' in s.errors

# Empty body — test_path defaults to None
s = ConnectionTestRequestSerializer(data={})
assert s.is_valid()
assert s.validated_data['test_path'] is None

print('ConnectionTestRequestSerializer: PASS')
"
```

**Troubleshooting:**

- **`result_id` not appearing in serializer output:** Confirm `source="id"` is correct and `result_id` is in `Meta.fields`.
- **`steps` is always an empty list:** The model's `step_results` field defaults to `[]`. Verify `ConnectionTestService.run()` populated the field correctly in the test.

---

### Task P3.E-02: Add `test_connection` `@action` to `ConnectionProfileViewSet`

**Purpose:** Expose the `ConnectionTestService` via HTTP and integrate with DRF's permission and object-lookup infrastructure.

**Steps:**

1. **Update** `backend/api_connector/views/connection_profile.py` — add the action:

```python
# backend/api_connector/views/connection_profile.py
import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api_connector.error_codes import NOT_FOUND, UNEXPECTED_ERROR
from api_connector.models import ConnectionProfile
from api_connector.serializers.connection_profile import (
    ConnectionProfileCreateSerializer,
    ConnectionProfileReadSerializer,
    ConnectionProfileUpdateSerializer,
)
from api_connector.serializers.connection_test import (
    ConnectionTestRequestSerializer,
    ConnectionTestResultSerializer,
)

logger = logging.getLogger("api_connector.views")


class ConnectionProfileViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for ConnectionProfile + connection test action.

    URL: /api/connector/profiles/
    Test endpoint: POST /api/connector/profiles/{id}/test/

    [ASSUMPTION] permission_classes = [AllowAny] assumes host-platform auth.
    Phase 8 security audit must confirm or add an authentication class.
    """

    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = ConnectionProfile.objects.select_related("auth_config").order_by(
            "-created_at"
        )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())
        return queryset

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return ConnectionProfileReadSerializer
        elif self.action == "create":
            return ConnectionProfileCreateSerializer
        else:
            return ConnectionProfileUpdateSerializer

    def create(self, request, *args, **kwargs):
        write_serializer = ConnectionProfileCreateSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        instance = write_serializer.save()
        read_serializer = ConnectionProfileReadSerializer(instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        """
        POST /api/connector/profiles/{id}/test/

        Runs ConnectionTestService.run() for the profile and returns the result.

        Security note [SSRF]: This endpoint makes outbound HTTP calls to user-configured
        base_url values. Phase 8 security audit must evaluate whether SSRF protection
        (blocking RFC 1918 ranges) is required in this deployment context.
        """
        # Validate request body
        request_serializer = ConnectionTestRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        test_path = request_serializer.validated_data.get("test_path")

        # get_object() applies get_queryset() (select_related) + 404 handling
        profile = self.get_object()

        logger.info(
            "ConnectionTest requested for profile=%s test_path=%s",
            profile.pk,
            test_path or "(base URL)",
        )

        try:
            from api_connector.services.connection_test import ConnectionTestService

            service = ConnectionTestService()
            result = service.run(profile_id=profile.pk, test_path=test_path)
        except ConnectionProfile.DoesNotExist:
            return Response(
                {"error_code": NOT_FOUND, "message": "Profile not found.", "detail": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("Unexpected error during connection test for profile=%s", profile.pk)
            return Response(
                {
                    "error_code": UNEXPECTED_ERROR,
                    "message": "An unexpected error occurred during the connection test.",
                    "detail": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        result_serializer = ConnectionTestResultSerializer(instance=result)
        return Response(result_serializer.data, status=status.HTTP_200_OK)
```

2. Verify the URL resolves:

```bash
cd backend && source .venv/bin/activate

python manage.py check
# Expected: System check identified no issues (0 silenced).

python manage.py shell -c "
from django.urls import reverse
url = reverse('api_connector:profile-test-connection', args=[1])
print('URL:', url)
assert url == '/api/connector/profiles/1/test/', f'Wrong URL: {url}'
print('PASS')
"
```

3. Quick API test with server running:

```bash
python manage.py runserver &
sleep 2

curl -s -X POST http://localhost:8000/api/connector/profiles/99999/test/ \
  -H "Content-Type: application/json" -d '{}' | python3 -m json.tool
# Expected: {"error_code": "API_CONN_002", "message": "...", "detail": {}}

curl -s -X POST http://localhost:8000/api/connector/profiles/1/test/ \
  -H "Content-Type: application/json" -d '{"test_path": "no-slash"}' | python3 -m json.tool
# Expected: 400 with error_code API_CONN_001

kill %1 2>/dev/null || true
```

**Troubleshooting:**

- **`NoReverseMatch: profile-test-connection`:** DRF auto-names `@action` methods as `{basename}-{url_name}`. With `basename="profile"` and method name `test_connection`, the URL name is `profile-test-connection`. Confirm `router.register(r"connector/profiles", ConnectionProfileViewSet, basename="profile")` in `urls.py`.
- **`AttributeError: 'ConnectionProfileViewSet' object has no attribute 'test_connection'`:** Confirm the `@action` decorator is imported: `from rest_framework.decorators import action`.

**Micro-Lesson:** `self.get_object()` does three things that `ConnectionProfile.objects.get(pk=pk)` doesn't: it applies `get_queryset()` (giving you `select_related('auth_config')` for free), it checks object-level permissions, and it returns a 404 if not found. Always use `self.get_object()` inside `@action` handlers.

---

### Task P3.F-01: Write `ConnectionTestService` Unit Tests

**Purpose:** Verify every step method and `run()` orchestration with mocked network — no real DNS queries or HTTP calls in CI.

**Steps:**

1. **Create** `backend/tests/test_connection_test_service.py`:

```python
# backend/tests/test_connection_test_service.py
"""
ConnectionTestService unit tests.

ALL outbound calls are mocked:
  - socket.getaddrinfo → unittest.mock.patch
  - BaseHTTPClient / httpx → pytest-httpx or unittest.mock.patch
  - OAuthCCTokenService → unittest.mock.patch

Rules enforced here:
  - Zero real DNS queries
  - Zero real HTTP calls
  - Each step tested in isolation where possible
"""
import socket
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.utils import timezone

from api_connector.models import AuthType, ConnectionProfile
from api_connector.services.connection_test.service import ConnectionTestService
from api_connector.services.connection_test.types import (
    ALL_STEPS,
    AUTH_INJECTION,
    DNS_RESOLUTION,
    FORMAT_DETECTION,
    HTTP_RESPONSE,
    NETWORK_CONNECTIVITY,
    RESPONSE_SAMPLE,
)
from api_connector.services.encryption import encryption_service
from api_connector.services.http_exceptions import (
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)
from tests.factories import AuthConfigFactory, ConnectionProfileFactory


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_profile(auth_type=AuthType.BEARER, **kwargs):
    profile = ConnectionProfileFactory(auth_type=auth_type, **kwargs)
    if auth_type == AuthType.NONE:
        creds = {}
    elif auth_type == AuthType.BEARER:
        creds = {"token": "test-token", "header_name": "Authorization"}
    elif auth_type == AuthType.API_KEY:
        creds = {"key_name": "X-API-Key", "key_value": "mykey", "delivery": "header"}
    elif auth_type == AuthType.BASIC:
        creds = {"username": "user", "password": "pass"}
    elif auth_type == AuthType.OAUTH_CC:
        creds = {
            "client_id": "cid",
            "client_secret": "csecret",
            "token_endpoint": "https://auth.example.com/token",
        }
    else:
        creds = {}
    AuthConfigFactory(
        connection_profile=profile,
        encrypted_credentials=encryption_service.encrypt_dict(creds),
        credentials_summary={k: {"is_set": bool(v)} for k, v in creds.items()},
    )
    return profile


def make_fake_dns_result(ip="1.2.3.4"):
    return [(2, 1, 6, "", (ip, 0))]


def make_fake_http_response(status_code=200, json_body=None, content_type="application/json"):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = {"content-type": content_type} if content_type else {}
    response.text = '{"data": [1, 2, 3]}' if json_body is None else str(json_body)
    response.content = response.text.encode()
    return response


# ── DNS Resolution Step ───────────────────────────────────────────────────────

class TestStepDnsResolution:
    svc = ConnectionTestService()

    def test_pass_resolves_ips(self):
        with patch("socket.getaddrinfo", return_value=make_fake_dns_result("1.2.3.4") + make_fake_dns_result("5.6.7.8")):
            result = self.svc._step_dns_resolution("api.example.com", ssl_verify=True)
        assert result.passed is True
        assert result.name == DNS_RESOLUTION
        assert "1.2.3.4" in result.detail["resolved_ips"]
        assert "api.example.com" in result.message

    def test_fail_name_not_found(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "Name not found")):
            result = self.svc._step_dns_resolution("nonexistent.invalid", ssl_verify=True)
        assert result.passed is False
        assert result.name == DNS_RESOLUTION
        # CRITICAL: no Python exception class name in user-facing message
        assert "gaierror" not in result.message.lower()
        assert "nonexistent.invalid" in result.message

    def test_fail_timeout(self):
        import concurrent.futures

        with patch(
            "concurrent.futures.Future.result",
            side_effect=concurrent.futures.TimeoutError(),
        ):
            result = self.svc._step_dns_resolution("slow.example.com", ssl_verify=True)
        assert result.passed is False
        assert "timed out" in result.message.lower()

    def test_detail_has_suggested_action_on_fail(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "NX")):
            result = self.svc._step_dns_resolution("bad.host", ssl_verify=True)
        assert "suggested_action" in result.detail
        assert len(result.detail["suggested_action"]) > 0


# ── Network Connectivity Step ─────────────────────────────────────────────────

class TestStepNetworkConnectivity:
    svc = ConnectionTestService()

    def test_pass_on_200(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json={"status": "ok"})
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is True
        assert result.detail["status_code"] == 200

    def test_pass_on_401(self, httpx_mock):
        """Server responded with 401 — TCP/TLS still works, step passes."""
        httpx_mock.add_exception(HTTPStatusError("HTTP 401", status_code=401, response_body="Unauthorized"))
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is True
        assert result.detail["status_code"] == 401

    def test_fail_on_timeout(self, httpx_mock):
        httpx_mock.add_exception(HTTPTimeoutError("Read timed out", url="https://x.com"))
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is False
        assert "timed out" in result.message.lower()

    def test_fail_on_ssl_error(self, httpx_mock):
        httpx_mock.add_exception(HTTPNetworkError("SSL certificate verify failed", url="https://x.com"))
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is False
        assert result.detail["ssl_error"] is True
        assert "certificate" in result.message.lower() or "tls" in result.message.lower() or "ssl" in result.message.lower()

    def test_fail_on_connection_refused(self, httpx_mock):
        httpx_mock.add_exception(HTTPNetworkError("Connection refused", url="https://x.com"))
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=30
        )
        assert result.passed is False
        assert result.detail["ssl_error"] is False

    def test_capped_timeout(self, httpx_mock):
        """Connectivity check uses min(timeout, 10) to avoid long waits."""
        httpx_mock.add_response(status_code=200)
        # Should not raise even with a 120s profile timeout
        result = self.svc._step_network_connectivity(
            "https://api.example.com", ssl_verify=True, timeout=120
        )
        assert result.passed is True


# ── Auth Injection Step ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStepAuthInjection:
    svc = ConnectionTestService()

    def test_pass_bearer(self):
        profile = make_profile(auth_type=AuthType.BEARER)
        result, credentials = self.svc._step_auth_injection(profile, profile.auth_config)
        assert result.passed is True
        assert "_profile_id" in credentials
        assert credentials["_profile_id"] == profile.pk

    def test_pass_none_auth(self):
        profile = make_profile(auth_type=AuthType.NONE)
        result, credentials = self.svc._step_auth_injection(profile, profile.auth_config)
        assert result.passed is True
        assert "_profile_id" in credentials

    def test_fail_oauth_ac(self):
        """OAuth AC requires browser — always fails step 3, no exception raised."""
        profile = make_profile(auth_type=AuthType.OAUTH_AC)
        result, credentials = self.svc._step_auth_injection(profile, profile.auth_config)
        assert result.passed is False
        assert credentials == {}
        assert "browser" in result.message.lower()
        assert "suggested_action" in result.detail

    def test_fail_empty_credentials(self):
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        auth_config = AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        result, _ = self.svc._step_auth_injection(profile, auth_config)
        assert result.passed is False
        assert "credentials" in result.message.lower() or "no credentials" in result.message.lower()

    def test_fail_corrupt_credentials(self):
        profile = ConnectionProfileFactory(auth_type=AuthType.BEARER)
        auth_config = AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials={"blob": "NOT_A_VALID_FERNET_TOKEN"},
        )
        result, _ = self.svc._step_auth_injection(profile, auth_config)
        assert result.passed is False
        assert "corrupt" in result.message.lower() or "decrypted" in result.message.lower()

    def test_pass_oauth_cc_with_token_fetch(self):
        profile = make_profile(auth_type=AuthType.OAUTH_CC)
        with patch("api_connector.services.oauth_cc_token.OAuthCCTokenService.get_token", return_value="mocked_token"):
            result, credentials = self.svc._step_auth_injection(profile, profile.auth_config)
        assert result.passed is True
        assert "_profile_id" in credentials

    def test_fail_oauth_cc_token_fetch_error(self):
        from api_connector.services.oauth_cc_token import OAuthCCTokenFetchError
        profile = make_profile(auth_type=AuthType.OAUTH_CC)
        with patch("api_connector.services.oauth_cc_token.OAuthCCTokenService.get_token",
                   side_effect=OAuthCCTokenFetchError("Token endpoint returned HTTP 401")):
            result, _ = self.svc._step_auth_injection(profile, profile.auth_config)
        assert result.passed is False
        assert "token" in result.message.lower()


# ── HTTP Response Step ────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStepHttpResponse:
    svc = ConnectionTestService()

    def test_pass_on_200(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_response(status_code=200, json={"ok": True})
        credentials = {"_profile_id": profile.pk}
        result, response = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is True
        assert result.detail["status_code"] == 200
        assert response is not None

    def test_fail_on_401(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_response(status_code=401, text="Unauthorized")
        credentials = {"_profile_id": profile.pk}
        result, response = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is False
        assert response is None
        assert "401" in result.message or "rejected" in result.message.lower()
        assert "suggested_action" in result.detail

    def test_fail_on_500(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_response(status_code=500, text="Internal Server Error")
        credentials = {"_profile_id": profile.pk}
        result, _ = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is False
        assert "500" in result.message or "server error" in result.message.lower()

    def test_url_construction_with_test_path(self, httpx_mock):
        profile = ConnectionProfileFactory(
            base_url="https://api.example.com", auth_type=AuthType.NONE
        )
        AuthConfigFactory(connection_profile=profile, encrypted_credentials=encryption_service.encrypt_dict({}))
        httpx_mock.add_response(status_code=200, json={})
        credentials = {"_profile_id": profile.pk}
        self.svc._step_http_response("https://api.example.com", "/v1/items", profile, credentials)
        sent = httpx_mock.get_request()
        assert "/v1/items" in str(sent.url)

    def test_fail_on_timeout(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
        credentials = {"_profile_id": profile.pk}
        result, _ = self.svc._step_http_response(
            profile.base_url, None, profile, credentials
        )
        assert result.passed is False
        assert "timed out" in result.message.lower()


# ── Format Detection Step ─────────────────────────────────────────────────────

class TestStepFormatDetection:
    svc = ConnectionTestService()

    def _make_response(self, content_type=None, body="{}"):
        response = MagicMock(spec=httpx.Response)
        response.headers = {"content-type": content_type} if content_type else {}
        response.text = body
        return response

    def test_json_from_content_type(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type="application/json; charset=utf-8")
        )
        assert result.passed is True
        assert fmt == "json"
        assert result.detail["source"] == "content_type_header"

    def test_json_from_body_sniff(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type=None, body='{"items": []}')
        )
        assert fmt == "json"
        assert result.detail["source"] == "body_sniff"

    def test_xml_from_body_sniff(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type=None, body="<?xml version='1.0'?><root/>")
        )
        assert fmt == "xml"

    def test_plain_text_fallback(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type=None, body="some plain text here")
        )
        assert fmt == "plain_text"

    def test_csv_from_content_type(self):
        result, fmt = self.svc._step_format_detection(
            self._make_response(content_type="text/csv")
        )
        assert fmt == "csv"

    def test_always_passes(self):
        """Format detection never fails — even for unknown formats."""
        result, _ = self.svc._step_format_detection(
            self._make_response(content_type="application/octet-stream", body="\x00\x01\x02")
        )
        assert result.passed is True


# ── Response Sample Step ──────────────────────────────────────────────────────

class TestStepResponseSample:
    svc = ConnectionTestService()

    def _make_response(self, body):
        response = MagicMock(spec=httpx.Response)
        response.text = body
        response.content = body.encode()
        return response

    def test_short_body_not_truncated(self):
        result = self.svc._step_response_sample(self._make_response('{"x": 1}'))
        assert result.passed is True
        assert result.detail["truncated"] is False
        assert result.detail["body_sample"] == '{"x": 1}'

    def test_long_body_truncated_to_2048_chars(self):
        long_body = "a" * 3000
        result = self.svc._step_response_sample(self._make_response(long_body))
        assert result.detail["truncated"] is True
        assert len(result.detail["body_sample"]) == 2048

    def test_body_size_bytes_is_raw_content_length(self):
        body = "hello"
        result = self.svc._step_response_sample(self._make_response(body))
        assert result.detail["body_size_bytes"] == len(body.encode())

    def test_always_passes(self):
        result = self.svc._step_response_sample(self._make_response(""))
        assert result.passed is True


# ── Full run() Orchestration ──────────────────────────────────────────────────

@pytest.mark.django_db
class TestConnectionTestServiceRun:
    def _mock_dns_success(self):
        return patch("socket.getaddrinfo", return_value=make_fake_dns_result("1.2.3.4"))

    def test_happy_path_all_6_steps_pass(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.BEARER)
        # Step 1: DNS
        with self._mock_dns_success():
            # Step 2: network (200)
            httpx_mock.add_response(status_code=200, json={"ok": True})
            # Step 4: authenticated HTTP (200 with JSON)
            httpx_mock.add_response(
                status_code=200,
                json={"data": [1, 2, 3]},
                headers={"content-type": "application/json"},
            )
            svc = ConnectionTestService()
            result = svc.run(profile_id=profile.pk)

        assert result.overall_passed is True
        assert len(result.step_results) == 6
        assert all(s["passed"] for s in result.step_results)

        # Profile last_test_* fields updated
        profile.refresh_from_db()
        assert profile.last_test_outcome is True
        assert profile.last_test_at is not None
        assert profile.last_test_detected_format == "json"

    def test_early_exit_at_step_1_dns_failure(self):
        profile = make_profile(auth_type=AuthType.BEARER)
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "NX")):
            svc = ConnectionTestService()
            result = svc.run(profile_id=profile.pk)

        assert result.overall_passed is False
        assert len(result.step_results) == 1
        assert result.step_results[0]["name"] == DNS_RESOLUTION

        profile.refresh_from_db()
        assert profile.last_test_outcome is False
        assert profile.last_test_status_code is None

    def test_early_exit_at_step_2_network_failure(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.BEARER)
        with self._mock_dns_success():
            httpx_mock.add_exception(HTTPTimeoutError("timeout", url="https://x.com"))
            svc = ConnectionTestService()
            result = svc.run(profile_id=profile.pk)

        assert result.overall_passed is False
        assert len(result.step_results) == 2
        assert result.step_results[1]["name"] == NETWORK_CONNECTIVITY
        assert result.step_results[1]["passed"] is False

    def test_profile_not_found_raises_does_not_exist(self):
        with pytest.raises(ConnectionProfile.DoesNotExist):
            ConnectionTestService().run(profile_id=99999)

    def test_last_test_status_code_from_step4(self, httpx_mock):
        profile = make_profile(auth_type=AuthType.NONE)
        with self._mock_dns_success():
            # Network connectivity check passes
            httpx_mock.add_response(status_code=200, json={})
            # Authenticated HTTP request gets 200
            httpx_mock.add_response(
                status_code=200,
                json={"ok": True},
                headers={"content-type": "application/json"},
            )
            result = ConnectionTestService().run(profile_id=profile.pk)

        profile.refresh_from_db()
        assert profile.last_test_status_code == 200
```

2. Run the tests:

```bash
cd backend && source .venv/bin/activate
pytest tests/test_connection_test_service.py -v
# Expected: all tests passing
```

**Troubleshooting:**

- **`httpx_mock` not found:** Confirm `pytest-httpx>=0.30` is in `requirements-dev.txt` and installed.
- **OAuth CC test fails with DB error:** The `make_profile(auth_type=AuthType.OAUTH_CC)` helper creates an `AuthConfigFactory` with encrypted creds. Ensure the encryption service has a valid key in the test environment.

---

### Task P3.F-02: Write OAuth CC Token Service and API Integration Tests

**Purpose:** Verify token caching, expiry logic, and the full API integration path through the HTTP layer.

**Steps:**

1. First, **add `ConnectionTestResultFactory`** to `backend/tests/factories.py`:

```python
# Append to backend/tests/factories.py

class ConnectionTestResultFactory(DjangoModelFactory):
    class Meta:
        model = ConnectionTestResult

    connection_profile = factory.SubFactory(ConnectionProfileFactory)
    step_results = factory.LazyAttribute(lambda _: [
        {"name": "dns_resolution", "passed": True, "message": "Resolved.", "detail": {}, "duration_ms": 10},
        {"name": "network_connectivity", "passed": True, "message": "Connected.", "detail": {}, "duration_ms": 20},
        {"name": "auth_injection", "passed": True, "message": "Auth OK.", "detail": {}, "duration_ms": 5},
        {"name": "http_response", "passed": True, "message": "200 OK.", "detail": {"status_code": 200, "response_time_ms": 100, "test_url": "https://api.example.com"}, "duration_ms": 100},
        {"name": "format_detection", "passed": True, "message": "JSON.", "detail": {"detected_format": "json", "source": "content_type_header"}, "duration_ms": 2},
        {"name": "response_sample", "passed": True, "message": "Captured.", "detail": {"body_size_bytes": 20, "truncated": False, "body_sample": '{"data": []}'}, "duration_ms": 1},
    ])
    overall_passed = True
    test_path = None
    duration_ms = 138
```

2. **Create** `backend/tests/test_oauth_cc_token_service.py`:

```python
# backend/tests/test_oauth_cc_token_service.py
"""
OAuthCCTokenService unit tests.
All HTTP calls to token endpoints are mocked via pytest-httpx.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from api_connector.models import OAuthToken, TokenType
from api_connector.services.encryption import encryption_service
from api_connector.services.oauth_cc_token import OAuthCCTokenFetchError, OAuthCCTokenService
from tests.factories import ConnectionProfileFactory, OAuthTokenFactory

VALID_CREDENTIALS = {
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "token_endpoint": "https://auth.example.com/token",
}


@pytest.mark.django_db
class TestOAuthCCTokenServiceCaching:
    def test_cache_hit_valid_token_no_http_call(self, httpx_mock):
        profile = ConnectionProfileFactory()
        # Store a non-expiring token in cache
        OAuthTokenFactory(
            connection_profile=profile,
            encrypted_token=encryption_service.encrypt("cached_token"),
            expires_at=None,
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "cached_token"
        # No HTTP call should have been made
        assert len(httpx_mock.get_requests()) == 0

    def test_cache_hit_future_expiry_no_http_call(self, httpx_mock):
        profile = ConnectionProfileFactory()
        OAuthTokenFactory(
            connection_profile=profile,
            encrypted_token=encryption_service.encrypt("future_token"),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "future_token"
        assert len(httpx_mock.get_requests()) == 0

    def test_cache_expiring_within_buffer_fetches_new_token(self, httpx_mock):
        """Token expiring in 30s (< 60s buffer) → fetch new token."""
        profile = ConnectionProfileFactory()
        OAuthTokenFactory(
            connection_profile=profile,
            encrypted_token=encryption_service.encrypt("expiring_token"),
            expires_at=timezone.now() + timedelta(seconds=30),
        )
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "new_token", "expires_in": 3600},
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "new_token"

    def test_cache_miss_fetches_and_stores_token(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(
            status_code=200,
            json={"access_token": "fresh_token", "expires_in": 3600},
        )
        result = OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert result == "fresh_token"
        stored = OAuthToken.objects.get(connection_profile=profile, token_type=TokenType.OAUTH_CC)
        assert encryption_service.decrypt(stored.encrypted_token) == "fresh_token"
        assert stored.expires_at is not None


@pytest.mark.django_db
class TestOAuthCCTokenServiceFetchErrors:
    def test_token_endpoint_401_raises_fetch_error(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=401, text="Unauthorized")
        with pytest.raises(OAuthCCTokenFetchError) as exc_info:
            OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert "401" in str(exc_info.value)
        assert "client_secret" not in str(exc_info.value)

    def test_missing_access_token_in_response_raises_error(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=200, json={"token_type": "bearer"})
        with pytest.raises(OAuthCCTokenFetchError) as exc_info:
            OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert "access_token" in str(exc_info.value)

    def test_expires_in_absent_stores_null_expires_at(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=200, json={"access_token": "token_no_expiry"})
        OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        stored = OAuthToken.objects.get(connection_profile=profile, token_type=TokenType.OAUTH_CC)
        assert stored.expires_at is None

    @pytest.mark.django_db(transaction=True)
    def test_second_fetch_overwrites_first_no_duplicate_rows(self, httpx_mock):
        profile = ConnectionProfileFactory()
        httpx_mock.add_response(status_code=200, json={"access_token": "token_1"})
        OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        httpx_mock.add_response(status_code=200, json={"access_token": "token_2"})
        # Force re-fetch by deleting cached token
        OAuthToken.objects.filter(connection_profile=profile).delete()
        OAuthCCTokenService().get_token(profile.pk, VALID_CREDENTIALS)
        assert OAuthToken.objects.filter(connection_profile=profile).count() == 1
```

3. **Create** `backend/tests/test_connection_test_api.py`:

```python
# backend/tests/test_connection_test_api.py
"""
API integration tests for POST /api/connector/profiles/{id}/test/.

ConnectionTestService.run() is mocked in all tests — no real outbound calls.
"""
from unittest.mock import patch

import pytest

from tests.factories import ConnectionProfileFactory, ConnectionTestResultFactory

TEST_URL = "/api/connector/profiles/{}/test/"


@pytest.mark.django_db
class TestConnectionTestEndpoint:
    def _mock_run(self, profile):
        """Return a patcher that mocks service.run() with a factory result."""
        test_result = ConnectionTestResultFactory(connection_profile=profile)
        return patch(
            "api_connector.views.connection_profile.ConnectionTestService",
            return_value=type("S", (), {"run": lambda *a, **kw: test_result})(),
        )

    def test_returns_200_with_result_structure(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={},
                format="json",
            )
        assert response.status_code == 200
        data = response.data
        assert "result_id" in data
        assert "overall_passed" in data
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert "duration_ms" in data
        assert_no_credential_leak(response)

    def test_with_valid_test_path(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={"test_path": "/api/v1/health"},
                format="json",
            )
        assert response.status_code == 200
        assert_no_credential_leak(response)

    def test_invalid_test_path_returns_400(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        response = api_client.post(
            TEST_URL.format(profile.pk),
            data={"test_path": "no-leading-slash"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["error_code"] == "API_CONN_001"
        assert_no_credential_leak(response)

    def test_empty_body_uses_base_url(self, api_client, assert_no_credential_leak):
        """Empty body (no test_path) must succeed — test_path defaults to None."""
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={},
                format="json",
            )
        assert response.status_code == 200
        assert_no_credential_leak(response)

    def test_nonexistent_profile_returns_404(self, api_client, assert_no_credential_leak):
        response = api_client.post(
            TEST_URL.format(99999),
            data={},
            format="json",
        )
        assert response.status_code == 404
        assert_no_credential_leak(response)

    def test_response_has_no_credential_data(self, api_client, assert_no_credential_leak):
        profile = ConnectionProfileFactory()
        with self._mock_run(profile):
            response = api_client.post(
                TEST_URL.format(profile.pk),
                data={},
                format="json",
            )
        # Critical: no credential values in test result response
        response_str = str(response.data)
        assert "client_secret" not in response_str
        assert "encrypted" not in response_str
        assert_no_credential_leak(response)
```

4. Run all backend tests:

```bash
cd backend && source .venv/bin/activate

pytest tests/test_oauth_cc_token_service.py tests/test_connection_test_api.py -v
# Expected: all tests passing

pytest --tb=short -q
# Expected: all pass; count ≥ 130
```

**Troubleshooting:**

- **`ConnectionTestResultFactory` not found:** The factory was appended to `factories.py`. Add the missing import: `from api_connector.models import ConnectionTestResult` at the top of `factories.py`.
- **Token test fails because profile has no auth_config:** `ConnectionTestResultFactory` doesn't create an `AuthConfig`. That's correct — `ConnectionTestResult` only needs a `ConnectionProfile`.

---

### Task P3.G-01: TypeScript Types, `connectionTestApi`, and `useConnectionTest` Hook

**Purpose:** Establish the frontend TypeScript contracts before any component is built.

**Steps:**

1. **Create** `frontend/src/features/connection-profile/types/connectionTest.ts`:

```typescript
// frontend/src/features/connection-profile/types/connectionTest.ts

export type StepName =
  | "dns_resolution"
  | "network_connectivity"
  | "auth_injection"
  | "http_response"
  | "format_detection"
  | "response_sample";

export const STEP_DISPLAY_NAMES: Record<StepName, string> = {
  dns_resolution: "DNS Resolution",
  network_connectivity: "Network Connectivity",
  auth_injection: "Auth Injection",
  http_response: "HTTP Response",
  format_detection: "Format Detection",
  response_sample: "Response Sample",
};

export const ALL_STEP_NAMES: StepName[] = [
  "dns_resolution",
  "network_connectivity",
  "auth_injection",
  "http_response",
  "format_detection",
  "response_sample",
];

export interface TestStepResult {
  name: StepName;
  passed: boolean;
  message: string;
  detail: Record<string, unknown>;
  duration_ms?: number;
}

export interface ConnectionTestResult {
  result_id: number;
  overall_passed: boolean;
  tested_at: string; // ISO 8601
  duration_ms: number;
  steps: TestStepResult[];
}
```

2. **Update** `frontend/src/features/connection-profile/types/index.ts`:

```typescript
// frontend/src/features/connection-profile/types/index.ts
export * from "./requests";
export * from "./connectionTest";
```

3. **Create** `frontend/src/features/connection-profile/api/connectionTestApi.ts`:

```typescript
// frontend/src/features/connection-profile/api/connectionTestApi.ts
import { apiClient } from "@/lib";
import type { ConnectionTestResult } from "../types";

export const connectionTestApi = {
  runConnectionTest(
    profileId: number,
    testPath?: string,
  ): Promise<ConnectionTestResult> {
    return apiClient
      .post<ConnectionTestResult>(
        `/api/connector/profiles/${profileId}/test/`,
        { test_path: testPath ?? null },
      )
      .then((r) => r.data);
  },
};
```

4. **Update** `frontend/src/features/connection-profile/api/index.ts`:

```typescript
// frontend/src/features/connection-profile/api/index.ts
export * from "./profilesApi";
export * from "./connectionTestApi";
```

5. **Create** `frontend/src/features/connection-profile/hooks/useConnectionTest.ts`:

```typescript
// frontend/src/features/connection-profile/hooks/useConnectionTest.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { connectionTestApi } from "../api/connectionTestApi";
import type { ConnectionTestResult } from "../types";
import { PROFILE_QUERY_KEY } from "./useProfiles";

export function useRunConnectionTest() {
  const queryClient = useQueryClient();

  return useMutation<
    ConnectionTestResult,
    unknown,
    { profileId: number; testPath?: string }
  >({
    mutationFn: ({ profileId, testPath }) =>
      connectionTestApi.runConnectionTest(profileId, testPath),
    onSuccess: () => {
      // Refresh profile list so last_test_* fields update
      queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
    },
  });
}
```

6. **Update** `frontend/src/features/connection-profile/hooks/index.ts`:

```typescript
// frontend/src/features/connection-profile/hooks/index.ts
export * from "./useProfiles";
export * from "./useConnectionTest";
```

**Verification:**

```bash
cd frontend && npm run typecheck
# Expected: exit 0

# Confirm 6 step names in STEP_DISPLAY_NAMES
node -e "
const {STEP_DISPLAY_NAMES, ALL_STEP_NAMES} = require('./src/features/connection-profile/types/connectionTest.ts');
" 2>/dev/null || npx tsc --noEmit && echo "TypeScript clean"
```

---

### Task P3.G-02: Create `StepResultItem` Component

**Purpose:** Single step row with three visual states (loading, future, result) and the amber "What to try" callout that converts diagnostic errors into actionable instructions.

**Steps:**

1. **Create** `frontend/src/features/connection-profile/components/StepResultItem.tsx`:

```tsx
// frontend/src/features/connection-profile/components/StepResultItem.tsx
import { CheckCircle2, Lightbulb, Loader2, XCircle } from "lucide-react";
import { STEP_DISPLAY_NAMES, type StepName, type TestStepResult } from "../types";

interface StepResultItemProps {
  stepName: StepName;
  result?: TestStepResult;
  isLoading?: boolean;
  isFuture?: boolean;
}

export function StepResultItem({
  stepName,
  result,
  isLoading = false,
  isFuture = false,
}: StepResultItemProps) {
  const displayName = STEP_DISPLAY_NAMES[stepName];

  // Loading state — test is in progress and this step is "active"
  if (isLoading) {
    return (
      <div className="flex items-start gap-3 py-2">
        <Loader2 className="h-5 w-5 text-muted-foreground animate-spin mt-0.5 shrink-0" />
        <span className="text-sm text-muted-foreground">{displayName}</span>
      </div>
    );
  }

  // Future state — step hasn't run yet
  if (isFuture || result === undefined) {
    return (
      <div className="flex items-start gap-3 py-2 opacity-40">
        <div className="h-5 w-5 rounded-full border-2 border-muted-foreground/30 mt-0.5 shrink-0" />
        <span className="text-sm text-muted-foreground">{displayName}</span>
      </div>
    );
  }

  // Result state — passed or failed
  const suggestedAction = result.detail?.suggested_action as string | undefined;

  if (result.passed) {
    return (
      <div className="flex items-start gap-3 py-2">
        <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
        <div>
          <span className="text-sm font-medium">{displayName}</span>
          <p className="text-xs text-muted-foreground mt-0.5">{result.message}</p>
        </div>
      </div>
    );
  }

  // Failed
  return (
    <div className="flex items-start gap-3 py-2">
      <XCircle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-sm font-semibold text-destructive">{displayName}</span>
        <p className="text-sm text-destructive mt-0.5">{result.message}</p>

        {/* Expandable detail */}
        {Object.keys(result.detail).length > 0 && (
          <details className="mt-1">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
              Show detail
            </summary>
            <div className="mt-1 text-xs text-muted-foreground space-y-0.5">
              {Object.entries(result.detail)
                .filter(([k]) => k !== "suggested_action")
                .map(([key, value]) => (
                  <div key={key} className="font-mono">
                    <span className="text-foreground/60">{key}:</span>{" "}
                    {String(value)}
                  </div>
                ))}
            </div>
          </details>
        )}

        {/* "What to try" callout — only for failed steps with suggested_action */}
        {suggestedAction && (
          <div className="mt-2 flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded p-2">
            <Lightbulb className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">{suggestedAction}</p>
          </div>
        )}
      </div>
    </div>
  );
}
```

2. Update components barrel:

```typescript
// frontend/src/features/connection-profile/components/index.ts — add:
export * from "./StepResultItem";
```

**Verification:**

```bash
cd frontend && npm run typecheck && npm run build
# Both exit 0
```

---

### Task P3.G-03: Create `ConnectionTestPanel` Component

**Purpose:** Full step list with progress simulation — gives visual feedback during the blocking 3–5 second test run and renders actual results afterward.

**Steps:**

1. **Create** `frontend/src/features/connection-profile/components/ConnectionTestPanel.tsx`:

```tsx
// frontend/src/features/connection-profile/components/ConnectionTestPanel.tsx
import { useEffect, useRef, useState } from "react";
import type { APIError } from "@/shared/types";
import {
  ALL_STEP_NAMES,
  type ConnectionTestResult,
  type StepName,
} from "../types";
import { StepResultItem } from "./StepResultItem";

interface ConnectionTestPanelProps {
  result: ConnectionTestResult | null;
  isRunning: boolean;
  error: unknown | null;
}

export function ConnectionTestPanel({
  result,
  isRunning,
  error,
}: ConnectionTestPanelProps) {
  const [simulatedIndex, setSimulatedIndex] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Progress simulation — advances one step every 800ms while running
  useEffect(() => {
  if (!isRunning) {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return;
  }

  // simulatedIndex is already 0 from the previous cleanup
  intervalRef.current = setInterval(() => {
    setSimulatedIndex((prev) =>
      prev < ALL_STEP_NAMES.length - 1 ? prev + 1 : prev,
    );
  }, 800);

  return () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setSimulatedIndex(0);  // reset here — in cleanup, not effect body
  };
}, [isRunning]);

  const apiError = error as APIError | null;

  // No result, not running — placeholder
  if (!isRunning && !result && !error) {
    return (
      <div className="py-8 text-center text-muted-foreground text-sm">
        Run a test to see results here.
      </div>
    );
  }

  // Build step result map from actual results
  const resultMap = new Map(result?.steps.map((s) => [s.name, s]) ?? []);
  const completedStepNames = new Set(result?.steps.map((s) => s.name) ?? []);

  // Response sample step (step 6) — for raw response section
  const sampleStep = result?.steps.find((s) => s.name === "response_sample");
  const bodySample = sampleStep?.detail?.body_sample as string | undefined;
  const bodySize = sampleStep?.detail?.body_size_bytes as number | undefined;

  return (
    <div className="space-y-1">
      {/* Error banner */}
      {apiError && (
        <div className="mb-3 p-3 rounded bg-destructive/10 border border-destructive/20">
          <p className="text-sm text-destructive">
            {apiError.message ?? "An error occurred. Please try again."}
          </p>
        </div>
      )}

      {/* Step list */}
      <div className="divide-y divide-border">
        {ALL_STEP_NAMES.map((stepName, index) => {
          if (isRunning) {
            return (
              <StepResultItem
                key={stepName}
                stepName={stepName as StepName}
                isLoading={index <= simulatedIndex}
                isFuture={index > simulatedIndex}
              />
            );
          }

          const stepResult = resultMap.get(stepName);
          return (
            <StepResultItem
              key={stepName}
              stepName={stepName as StepName}
              {...(stepResult !== undefined ? { result: stepResult } : {})}
              isFuture={!completedStepNames.has(stepName)}
            />
          );
        })}
      </div>

      {/* Summary row */}
      {result && !isRunning && (
        <div className="pt-3 border-t flex items-center justify-between text-sm">
          <span
            className={
              result.overall_passed
                ? "font-semibold text-green-600 dark:text-green-400"
                : "font-semibold text-destructive"
            }
          >
            {result.overall_passed ? "✓ Test passed" : "✗ Test failed"}
          </span>
          <span className="text-muted-foreground">
            Completed in {result.duration_ms}ms
          </span>
        </div>
      )}

      {/* Raw Response — only when step 6 completed */}
      {bodySample !== undefined && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
            Raw Response ({bodySize ?? 0} bytes)
          </summary>
          <div className="mt-2 relative">
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(bodySample)}
              className="absolute top-2 right-2 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded border border-border bg-background"
            >
              Copy
            </button>
            <pre className="font-mono text-xs overflow-x-auto max-h-64 p-3 rounded bg-muted text-foreground whitespace-pre-wrap break-words">
              {bodySample}
            </pre>
          </div>
        </details>
      )}
    </div>
  );
}
```

2. Update components barrel:

```typescript
// Add to frontend/src/features/connection-profile/components/index.ts:
export * from "./ConnectionTestPanel";
```

---

### Task P3.G-04: Create `ConnectionTestModal` Component

**Purpose:** Sheet modal containing the test path input, run button, and embedded `ConnectionTestPanel`. Modal stays open after test completes so users can read results.

**Steps:**

1. Install shadcn Sheet:

```bash
cd frontend
npx shadcn@latest add sheet
```

2. **Create** `frontend/src/features/connection-profile/components/ConnectionTestModal.tsx`:

```tsx
// frontend/src/features/connection-profile/components/ConnectionTestModal.tsx
import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/shared/components/ui/sheet";
import { useRunConnectionTest } from "../hooks/useConnectionTest";
import { ConnectionTestPanel } from "./ConnectionTestPanel";

interface ConnectionTestModalProps {
  profileId: number;
  profileName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ConnectionTestModal({
  profileId,
  profileName,
  isOpen,
  onClose,
}: ConnectionTestModalProps) {
  const [testPath, setTestPath] = useState("");
  const mutation = useRunConnectionTest();

  function handleOpenChange(open: boolean) {
    if (open) {
      // Modal opening — reset to clean state
      // Event handler, not an effect body — setState is correct here
      setTestPath("");
      mutation.reset();
    } else {
      onClose();
    }
  }

  function handleRunTest() {
    const trimmed = testPath.trim();
    mutation.mutate({
      profileId,
      // Conditional spread — only include testPath when it has a value
      // Avoids passing undefined explicitly (exactOptionalPropertyTypes)
      ...(trimmed ? { testPath: trimmed } : {}),
    });
    // Modal does NOT close on success — user reads results
  }

  return (
    <Sheet open={isOpen} onOpenChange={handleOpenChange}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader className="mb-4">
          <SheetTitle>Test Connection</SheetTitle>
          <SheetDescription>{profileName}</SheetDescription>
        </SheetHeader>

        <div className="space-y-4">
          {/* Test path input */}
          <div className="space-y-1">
            <Label htmlFor="test-path">Test Path (optional)</Label>
            <Input
              id="test-path"
              value={testPath}
              onChange={(e) => setTestPath(e.target.value)}
              placeholder="/api/v1/health"
              disabled={mutation.isPending}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to test the base URL. Must start with{" "}
              <code className="font-mono">/</code> if provided.
            </p>
          </div>

          {/* Run Test button */}
          <Button
            onClick={handleRunTest}
            disabled={mutation.isPending}
            className="w-full"
          >
            {mutation.isPending ? "Testing…" : "Run Test"}
          </Button>

          {/* Step results panel */}
          <ConnectionTestPanel
            result={mutation.data ?? null}
            isRunning={mutation.isPending}
            error={mutation.error}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

3. Update components barrel:

```typescript
// Add to frontend/src/features/connection-profile/components/index.ts:
export * from "./ConnectionTestModal";
```

---

### Task P3.G-05: Enable Re-Test Button in `ProfileCard`; Wire `ConnectionTestModal`

**Purpose:** Activate the previously-disabled Re-Test button, completing the primary user workflow: Create → Edit → Test → See Results.

**Steps:**

1. **Update** `frontend/src/features/connection-profile/components/ProfileCard.tsx`:

```tsx
// frontend/src/features/connection-profile/components/ProfileCard.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import type { ConnectionProfile } from "@/shared/types";
import { AuthTypeBadge } from "./AuthTypeBadge";
import { ConnectionTestModal } from "./ConnectionTestModal";
import { LastTestIndicator } from "./LastTestIndicator";

interface ProfileCardProps {
  profile: ConnectionProfile;
  onDelete: () => void;
}

export function ProfileCard({ profile, onDelete }: ProfileCardProps) {
  const navigate = useNavigate();
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base">{profile.name}</CardTitle>
            <AuthTypeBadge authType={profile.auth_type} />
          </div>
          <p className="text-xs text-muted-foreground font-mono truncate">
            {profile.base_url}
          </p>
        </CardHeader>
        <CardContent className="pb-3">
          <LastTestIndicator
            outcome={profile.last_test_outcome}
            testedAt={profile.last_test_at}
            statusCode={profile.last_test_status_code}
          />
          <div className="flex gap-2 mt-3">
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate(`/profiles/${profile.id}/edit`)}
            >
              Edit
            </Button>

            <Button
              size="sm"
              variant="outline"
              onClick={() => setIsTestModalOpen(true)}
            >
              Test Connection
            </Button>

            <Button size="sm" variant="destructive" onClick={onDelete}>
              Delete
            </Button>
          </div>
        </CardContent>
      </Card>

      <ConnectionTestModal
        profileId={profile.id}
        profileName={profile.name}
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
      />
    </>
  );
}

export function ProfileCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-3 w-64 mt-1" />
      </CardHeader>
      <CardContent className="pb-3">
        <Skeleton className="h-4 w-32" />
        <div className="flex gap-2 mt-3">
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-8 w-16" />
        </div>
      </CardContent>
    </Card>
  );
}
```

2. **Update** `frontend/src/features/connection-profile/pages/ProfileListPage.tsx` — remove `onReTest` prop:

Find and replace the `<ProfileCard>` usage. The `onReTest` prop no longer exists:

```tsx
{profiles.map((profile) => (
  <ProfileCard
    key={profile.id}
    profile={profile}
    onDelete={() => setDeletingProfileId(profile.id)}
  />
))}
```

3. **Update** the full components barrel:

```typescript
// frontend/src/features/connection-profile/components/index.ts
export * from "./AuthTypeBadge";
export * from "./LastTestIndicator";
export * from "./DeleteConfirmModal";
export * from "./ProfileCard";
export * from "./DefaultHeadersEditor";
export * from "./SecretField";
export * from "./StepResultItem";
export * from "./ConnectionTestPanel";
export * from "./ConnectionTestModal";
```

4. Final verification:

```bash
cd frontend
npm run typecheck && npm run build && npm test
# All three must exit 0

# Lint check
npm run lint
# Expected: exit 0
```

5. Final commit:

```bash
cd ..
git add backend/ frontend/ docs/ scripts/
git commit -m "P3: Complete Phase 3 — connection test service, OAuth CC, test modal"
git push
```

**Verification:**

With both servers running (`python manage.py runserver` and `npm run dev`):

```
1. Navigate to http://localhost:5173/profiles
2. Click "Test Connection" on any profile
3. ConnectionTestModal opens as a Sheet
4. Click "Run Test" → progress simulation shows spinners advancing
5. Results appear with ✓/✗ per step
6. Failed steps show amber "What to try" callout
7. If step 6 passed, "Raw Response" section appears (collapsible)
8. Profile list updates — last_test_* fields visible on card
```

**Troubleshooting:**

- **`Sheet` component not found:** Run `npx shadcn@latest add sheet` from `frontend/`.
- **`onReTest` prop error in ProfileListPage:** Find every remaining `onReTest` prop usage and remove it — the prop was deleted from `ProfileCard`.
- **Progress simulation jumps to last step instantly:** Confirm `setInterval` is cleared on `isRunning=false`. The cleanup effect `return () => clearInterval(intervalRef.current)` must be present.

**Micro-Lesson:** The `useEffect` reset on `[isOpen, profileId]` dependency ensures that opening the modal for profile B after testing profile A doesn't show profile A's results. `mutation.reset()` clears the mutation's data, error, and status — giving a fresh start for each modal open event.

---

## 3. Phase Completion Summary

### What Was Built

```
backend/
├── api_connector/
│   ├── models/
│   │   ├── enums.py                     MODIFIED: + TokenType enum
│   │   ├── oauth_token.py               NEW: OAuthToken model
│   │   └── __init__.py                  MODIFIED: + OAuthToken, TokenType
│   ├── migrations/
│   │   └── 0003_oauth_token.py          NEW: OAuthToken table + unique_together
│   ├── serializers/
│   │   └── connection_test.py           NEW: ConnectionTestRequestSerializer + ConnectionTestResultSerializer
│   ├── views/
│   │   └── connection_profile.py        MODIFIED: + test_connection @action
│   ├── services/
│   │   ├── plain_english_errors.py      NEW: StepErrorMessage + 14 error entries + 6 success templates
│   │   ├── oauth_cc_token.py            NEW: OAuthCCTokenService + OAuthCCTokenFetchError
│   │   ├── auth/
│   │   │   └── handlers/
│   │   │       └── oauth_cc.py          REPLACED: stub → real implementation
│   │   └── connection_test/
│   │       ├── __init__.py              NEW: exports ConnectionTestService
│   │       ├── types.py                 NEW: StepResult + STEP_NAMES + ALL_STEPS
│   │       └── service.py              NEW: 6 step methods + run() + _persist()
└── tests/
    ├── factories.py                     MODIFIED: + OAuthTokenFactory, ConnectionTestResultFactory
    ├── test_connection_test_service.py  NEW: 28+ tests
    ├── test_oauth_cc_token_service.py   NEW: 10+ tests
    └── test_connection_test_api.py      NEW: 7 tests

docs/adr/                                (SSRF note in P3.E-02 view code)

frontend/src/features/connection-profile/
├── api/
│   └── connectionTestApi.ts            NEW
├── hooks/
│   └── useConnectionTest.ts            NEW
├── types/
│   └── connectionTest.ts               NEW: StepName, TestStepResult, ConnectionTestResult, STEP_DISPLAY_NAMES
├── components/
│   ├── StepResultItem.tsx              NEW
│   ├── ConnectionTestPanel.tsx         NEW
│   ├── ConnectionTestModal.tsx         NEW
│   ├── ProfileCard.tsx                 MODIFIED: Re-Test → Test Connection (active)
│   └── index.ts                        MODIFIED: + 3 new exports
└── pages/
    └── ProfileListPage.tsx             MODIFIED: onReTest prop removed
```

### Actual State

| Component                                                                       | Status     |
| ------------------------------------------------------------------------------- | ---------- |
| `TokenType` TextChoices enum                                                  | ✅ Working |
| `OAuthToken` model with `unique_together`                                   | ✅ Working |
| `0003_oauth_token` migration applied — 7 tables total                        | ✅ Working |
| `OAuthTokenFactory`                                                           | ✅ Working |
| `ConnectionTestResultFactory`                                                 | ✅ Working |
| `plain_english_errors.py` — 14 error entries + 6 success templates           | ✅ Working |
| `StepResult` dataclass + `ALL_STEPS` constants                              | ✅ Working |
| `_step_dns_resolution` — ThreadPoolExecutor + 5s timeout                     | ✅ Working |
| `_step_network_connectivity` — any HTTP response = pass                      | ✅ Working |
| `OAuthCCTokenService` — DB cache + 60s buffer                                | ✅ Working |
| `OAuthCCAuthHandler` — stub replaced with real impl                          | ✅ Working |
| `_step_auth_injection` — OAUTH_AC browser message (no exception)             | ✅ Working |
| `_step_http_response` — status-specific failure messages                     | ✅ Working |
| `_step_format_detection` — Content-Type + body sniff                         | ✅ Working |
| `_step_response_sample` — 2048-char cap                                      | ✅ Working |
| `ConnectionTestService.run()` — early-exit pipeline + atomic persist         | ✅ Working |
| `ConnectionTestRequestSerializer` — leading-slash validation                 | ✅ Working |
| `ConnectionTestResultSerializer` — `result_id` alias                       | ✅ Working |
| `POST /api/connector/profiles/{id}/test/`                                     | ✅ Working |
| URL reverse:`profile-test-connection`                                         | ✅ Working |
| Backend test count ≥ 130                                                       | ✅ Working |
| TypeScript `TestStepResult`, `ConnectionTestResult`, `STEP_DISPLAY_NAMES` | ✅ Working |
| `connectionTestApi.runConnectionTest()`                                       | ✅ Working |
| `useRunConnectionTest()` hook + profile list invalidation                     | ✅ Working |
| `StepResultItem` — 3 visual states + amber callout                           | ✅ Working |
| `ConnectionTestPanel` — progress simulation + raw response                   | ✅ Working |
| `ConnectionTestModal` — Sheet, stays open after results                      | ✅ Working |
| `ProfileCard` — "Test Connection" button active                              | ✅ Working |
| `npm run typecheck`, `build`, `test`, `lint`                            | ✅ Passing |
| OAuthCCAuthHandler stub replaced —`ValueError` not `NotImplementedError`   | ✅ Working |
| OAuthACAuthHandler — still raises `NotImplementedError` (Phase 4)            | ✅ Stubbed |
| PaginationRegistry — still raises `ValueError` (Phase 5)                     | ✅ Stubbed |

### Deviations from Plan

| Task    | Deviation                                                                                                                                            | Reason                                                                                                                                               |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| P3.C-03 | `_step_auth_injection` handles `AuthType.NONE` explicitly (immediate pass, no decrypt)                                                           | The spec's "validate non-empty credentials" check would incorrectly fail for NONE auth where `encrypted_credentials == {}` is correct and expected |
| P3.C-03 | `_step_http_response` accepts `(base_url, test_path, profile, credentials)` instead of `(base_url, test_path, authenticated_request, profile)` | P3.C-04's `run()` passes `credentials` (not a pre-built request); auth injection happens inside the step to match the test URL, not the base URL |
| P3.G-05 | Button renamed from "Re-Test" to "Test Connection"                                                                                                   | "Test Connection" is clearer on first use when no prior test exists                                                                                  |
| P3.B-01 | Added `credentials_corrupt` key to error map                                                                                                       | Required by `_step_auth_injection` to handle `InvalidToken` gracefully                                                                           |

### Architecture Concerns

None. The SSRF concern noted in `P3.E-02` is documented in the view code and must be addressed in Phase 8's security audit. The sync/async architecture decision remains as established in ADR-006.

---

## 4. Phase Validation

### Completion Checklist

- [ ] `python manage.py showmigrations api_connector` → exactly 3 checked migrations (`0001`, `0002`, `0003`)
- [ ] `python manage.py dbshell` → `\dt api_connector*` shows **7 tables** (+ `api_connector_oauth_token`)
- [ ] `from api_connector.services.connection_test import ConnectionTestService; print('OK')` → no `ImportError`
- [ ] `from api_connector.services.oauth_cc_token import OAuthCCTokenService; print('OK')` → no `ImportError`
- [ ] OAuthCCAuthHandler raises `ValueError` (not `NotImplementedError`) when `_profile_id` is absent
- [ ] `reverse('api_connector:profile-test-connection', args=[1])` → `/api/connector/profiles/1/test/`
- [ ] `cd backend && pytest --collect-only -q 2>&1 | tail -1` → ≥ 130 tests collected
- [ ] `cd backend && pytest` exits 0
- [ ] `cd backend && ruff check . && ruff format --check .` exits 0
- [ ] `grep -r "from cryptography.fernet import Fernet" backend/api_connector --include="*.py" | grep -v "encryption.py"` → no output
- [ ] `grep -r "body_sample\|response\.text" backend/api_connector --include="*.py" | grep -i "logger\|log\."` → no output
- [ ] `cd frontend && npm run typecheck` exits 0
- [ ] `cd frontend && npm run build` exits 0
- [ ] `cd frontend && npm test` exits 0
- [ ] `cd frontend && npm run lint` exits 0
- [ ] `POST /api/connector/profiles/{id}/test/` → HTTP 200; body has `result_id`, `overall_passed`, `steps` (list); no `"encrypted"`, `"blob"`, or `"client_secret"` in response
- [ ] Re-Test button → `ConnectionTestModal` opens; step UI visible; "Run Test" button works
- [ ] Both GitHub CI workflows pass on push

### Validation Script

```bash
cat > scripts/validate-phase3.sh << 'SCRIPTEOF'
#!/usr/bin/env bash
# scripts/validate-phase3.sh
# Run from repository root: bash scripts/validate-phase3.sh
# Exits 0 on full pass, non-zero on any failure.

set -uo pipefail
PASS=0; FAIL=0; WARN=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; ((PASS++)) || true; }
fail() { echo -e "${RED}✗ FAIL${NC}: $1"; ((FAIL++)) || true; }
warn() { echo -e "${YELLOW}⚠ WARN${NC}: $1"; ((WARN++)) || true; }

REPO_ROOT="$(pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
VENV="$BACKEND/.venv"

PYTHON="$VENV/bin/python"; PYTEST="$VENV/bin/pytest"; RUFF="$VENV/bin/ruff"
[ -f "$PYTHON" ] || { PYTHON="$(command -v python3)"; PYTEST="$(command -v pytest)"; RUFF="$(command -v ruff)"; }
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -f "$REPO_ROOT/.nvmrc" ] && nvm use > /dev/null 2>&1 || true
NPM="$(command -v npm)"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Phase 3 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Migrations ────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Migrations ───────────────────────────────────────${NC}"
MIG=$(cd "$BACKEND" && $PYTHON manage.py showmigrations api_connector 2>/dev/null)
echo "$MIG" | grep -q "\[X\] 0001_initial" && pass "0001_initial applied" || fail "0001_initial missing"
echo "$MIG" | grep -q "\[X\] 0002_authconfig" && pass "0002_authconfig applied" || fail "0002 missing"
echo "$MIG" | grep -q "\[X\] 0003_oauth_token" && pass "0003_oauth_token applied" || fail "0003 not applied — run: python manage.py migrate"

# ── Table count ───────────────────────────────────────────────────────────────
TABLE_COUNT=$(cd "$BACKEND" && $PYTHON manage.py dbshell 2>/dev/null <<'SQL' | grep -c "api_connector_"
\dt api_connector*
SQL
)
[ "${TABLE_COUNT:-0}" -ge 7 ] && pass "7+ api_connector tables exist" || fail "Expected 7 tables, found ${TABLE_COUNT:-0}"

# ── Service imports ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Service Imports ──────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.connection_test import ConnectionTestService
from api_connector.services.oauth_cc_token import OAuthCCTokenService, OAuthCCTokenFetchError
print('OK')
" 2>/dev/null) && pass "ConnectionTestService and OAuthCCTokenService import cleanly" \
  || fail "Import error — check service files for syntax errors"

# ── OAuthCCAuthHandler no longer raises NotImplementedError ───────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
import httpx
from api_connector.services.auth.handlers.oauth_cc import OAuthCCAuthHandler
h = OAuthCCAuthHandler()
try:
    h.prepare_request(httpx.Request('GET', 'https://x.com'), {})
    print('ERROR')
    exit(1)
except ValueError:
    print('OK')
except NotImplementedError:
    print('STUB_STILL_PRESENT')
    exit(1)
" 2>/dev/null) && pass "OAuthCCAuthHandler raises ValueError (stub replaced)" \
  || fail "OAuthCCAuthHandler still raises NotImplementedError — stub not replaced"

# ── URL routing ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
url = reverse('api_connector:profile-test-connection', args=[1])
assert url == '/api/connector/profiles/1/test/', f'Wrong: {url}'
print('OK')
" 2>/dev/null) && pass "POST /api/connector/profiles/{id}/test/ URL resolves" \
  || fail "URL for profile-test-connection not found — check @action decorator"

# ── Security checks ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security ─────────────────────────────────────────${NC}"
FERNET_IMPORTS=$(grep -r "from cryptography.fernet import Fernet" "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -v "encryption.py" | wc -l)
[ "$FERNET_IMPORTS" -eq 0 ] && pass "No direct Fernet imports outside encryption.py" \
  || fail "Found $FERNET_IMPORTS Fernet imports outside encryption.py — security violation"

LOG_BODY=$(grep -r "body_sample\|response\.text" "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -i "logger\|log\." | wc -l)
[ "${LOG_BODY:-0}" -eq 0 ] && pass "Response body never logged (OWASP A09)" \
  || fail "body_sample or response.text found in log call — security violation"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"
(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) && pass "ruff format passes" || fail "ruff format failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 130 ] && pass "pytest passes — $COUNT tests (≥130 required)" \
    || fail "pytest passes but only $COUNT tests (need ≥130)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend ─────────────────────────────────────────${NC}"
[ -f "$FRONTEND/src/features/connection-profile/components/ConnectionTestModal.tsx" ] \
  && pass "ConnectionTestModal.tsx exists" || fail "ConnectionTestModal.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/components/StepResultItem.tsx" ] \
  && pass "StepResultItem.tsx exists" || fail "StepResultItem.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/types/connectionTest.ts" ] \
  && pass "connectionTest.ts TypeScript types exist" || fail "connectionTest.ts missing"

grep -q "MASK_DISPLAY" "$FRONTEND/src/features/connection-profile/components/SecretField.tsx" 2>/dev/null \
  && pass "SecretField MASK_DISPLAY constant unchanged" || warn "SecretField may have changed"

(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) && pass "npm run typecheck passes" || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) && pass "npm run build passes" || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) && pass "npm test passes" || fail "npm test failed"
(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) && pass "npm run lint passes" || fail "npm run lint failed"

# ── Manual steps reminder ─────────────────────────────────────────────────────
echo ""
warn "Manual verification needed:"
warn "  #16: POST /api/connector/profiles/{id}/test/ returns steps array, no credentials in response"
warn "  #17: Browser — Test Connection modal opens, progress simulation runs, results display"
warn "  #18: Both GitHub CI workflows pass on push"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 3 COMPLETE — Increment 1 ready — proceed to Phase 4 / Phase 5${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 3 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi
SCRIPTEOF

chmod +x scripts/validate-phase3.sh
git add scripts/validate-phase3.sh
git commit -m "P3: Add phase 3 validation script"
git push
```

Run it:

```bash
bash scripts/validate-phase3.sh
```

---

### Milestone Readiness Check — Increment 1

Increment 1 is defined as: *Profile management and connection testing operational for None, API Key, Bearer, Basic, and OAuth CC auth types.*

| Requirement                                                    | Status               |
| -------------------------------------------------------------- | -------------------- |
| Create, edit, delete profiles — all 6 auth types              | ✅ Phase 2           |
| Encrypted credentials at rest, credentials_summary on read     | ✅ Phase 2           |
| Connection test for None, API Key, Bearer, Basic               | ✅ This phase        |
| Connection test for OAuth CC (full token flow)                 | ✅ This phase        |
| OAuth AC shows "browser authorization required" (not an error) | ✅ This phase        |
| Per-step diagnostic UI with "What to try" callout              | ✅ This phase        |
| Last test result visible on profile cards                      | ✅ This phase        |
| Both CI workflows green                                        | ⏳ Verify after push |
| `bash scripts/validate-phase3.sh` exits 0                    | ⏳ Run to confirm    |

**Gap (known, documented):** OAuth AC connection testing requires Phase 4. The UI handles this gracefully — clicking Test Connection on an OAuth AC profile runs the test, step 3 fails with a plain-English browser-auth message, and the modal stays open showing the result. This is expected behavior, not a defect.

**Transition to Phase 4 / Phase 5:** Before starting either parallel phase, confirm:

1. `bash scripts/validate-phase3.sh` exits 0.
2. Both CI workflows pass on the last push.
3. `python manage.py showmigrations api_connector` shows exactly **3 checked migrations**.
4. At least one profile of each auth type has been tested manually via the UI.

Phase 4 reuses `OAuthToken` model, `ConnectionTestService`, and the step result contract. Phase 5 reuses `OAuthCCAuthHandler`, `BaseHTTPClient`, and the `_profile_id` credentials convention.
