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

        except Exception as exc:
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
                detail={
                    "status_code": response.status_code,
                    "response_time_ms": duration_ms,
                },
                duration_ms=duration_ms,
            )

        except HTTPStatusError as exc:
            # 4xx/5xx: server responded → TCP+TLS succeeded → PASS
            duration_ms = int((time.monotonic() - start) * 1000)
            return StepResult(
                name=NETWORK_CONNECTIVITY,
                passed=True,
                message=NETWORK_SUCCESS_MSG.format(status_code=exc.status_code),
                detail={
                    "status_code": exc.status_code,
                    "response_time_ms": duration_ms,
                },
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
            is_ssl = (
                "ssl" in error_str or "certificate" in error_str or "tls" in error_str
            )
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
            error_msg = STEP_ERROR_MESSAGES[
                ("auth_injection", "oauth_ac_browser_required")
            ]
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
                    message=AUTH_SUCCESS_MSG.format(
                        auth_type="none (no credentials required)"
                    ),
                    detail={"auth_type": auth_type, "credentials_present": False},
                    duration_ms=duration_ms,
                ),
                {"_profile_id": profile.pk},
            )

        # All other auth types — decrypt and validate
        try:
            decrypted = encryption_service.decrypt_to_dict(
                auth_config.encrypted_credentials
            )
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
                error_msg = STEP_ERROR_MESSAGES[
                    ("auth_injection", "oauth_cc_token_fetch_failed")
                ]
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
        test_path: str | None,
        profile: ConnectionProfile,
        credentials: dict,
    ) -> tuple[StepResult, httpx.Response | None]:
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
            base_headers = {
                h["name"]: h["value"]
                for h in (profile.default_headers or [])
                if h.get("name") and h.get("value")
            }
            
            request = httpx.Request("GET", test_url, headers=base_headers)
            auth_request = handler.prepare_request(request, credentials)

            with httpx.Client(
                verify=profile.ssl_verify, timeout=profile.request_timeout
            ) as client:
                response = client.send(auth_request)

            duration_ms = int((time.monotonic() - start) * 1000)

            # Log structural metadata only — no URL query string, no headers, no body
            url_no_qs = test_url.split("?")[0]
            logger.info(
                "HTTP GET %s → %s (%dms)", url_no_qs, response.status_code, duration_ms
            )

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

    def run(
        self,
        profile_id: int,
        test_path: str | None = None,
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
        result, _detected_format = self._step_format_detection(http_response)
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
        test_path: str | None,
        run_start: float,
    ) -> ConnectionTestResult:
        """
        Atomically save ConnectionTestResult and update ConnectionProfile.last_test_* fields.

        Uses queryset.update() (not instance.save()) to avoid overwriting fields
        concurrently edited by another request.
        """
        overall_passed = len(steps_completed) == len(ALL_STEPS) and all(
            s.passed for s in steps_completed
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
                last_test_status_code=step4.detail.get("status_code")
                if step4
                else None,
                last_test_response_time=step4.detail.get("response_time_ms")
                if step4
                else None,
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
