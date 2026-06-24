# backend/api_connector/services/pagination/engine.py
"""
PaginationEngine — generator-based pagination driver.

ADR-010: paginate() is a Python generator (uses yield).
  Callers (Phase 6 schema inference, Phase 7 data preview) iterate using
  for/next protocol. This enables early-exit without fetching all pages.
  Phase 6 can stop after 3 pages; Phase 7 can stop at row_limit.
  This is IRREVERSIBLE — callers depend on generator protocol.

Security:
  Log page count, records fetched, and latency. NEVER log response body.
  _next_url from API responses is followed unconditionally (SSRF concern —
  Phase 8 audit must evaluate RFC 1918 blocking).
"""

import json
import logging
import time
from collections.abc import Generator

import httpx

from api_connector.services.auth.base import BaseAuthHandler
from api_connector.services.http_exceptions import (
    HTTPNetworkError,
    HTTPStatusError,
    HTTPTimeoutError,
)
from api_connector.services.pagination.base import BasePaginationStrategy
from api_connector.services.pagination.types import PaginatedResponse, SafetyConfig
from api_connector.services.pagination.utils import (
    build_request_url,
    extract_records_at_path,
)

logger = logging.getLogger("api_connector.pagination_engine")


class PaginationEngineError(Exception):
    """
    Base class for errors raised by PaginationEngine.
    Safe to surface to the user — never contains raw response bodies.
    """


class PaginationSafetyLimitError(PaginationEngineError):
    """
    Raised when safety limits are hit mid-pagination (informational).
    The engine typically stops the generator silently (via return)
    rather than raising this — callers check page_count themselves.
    """


class PaginationEngine:
    """
    Stateless pagination engine. All state is maintained in local variables
    within paginate(). Thread-safe; create one instance and reuse.
    """

    def paginate(
        self,
        endpoint,
        auth_handler: BaseAuthHandler,
        credentials: dict,
        strategy: BasePaginationStrategy,
        safety: SafetyConfig,
        row_limit: int | None = None,
    ) -> Generator[list[dict], None, None]:
        """
        Drive all 6 pagination strategies, yielding one list of records per page.

        Args:
            endpoint: Endpoint model instance (needs .connection_profile, .path,
                      .path_variables, .query_params, .data_root_path,
                      .endpoint_headers).
            auth_handler: Injects auth into each request.
            credentials: Decrypted credentials dict (with _profile_id).
            strategy: Instantiated pagination strategy.
            safety: Hard stop limits (max_pages, max_records, etc.).
            row_limit: Optional; stop after this many total records (Phase 7).

        Yields:
            list[dict] — one page of records per iteration.

        Raises:
            PaginationEngineError: on JSON decode failure or other fatal errors.
            HTTPStatusError, HTTPTimeoutError, HTTPNetworkError: HTTP failures
                propagate to the caller on next().
        """
        profile = endpoint.connection_profile

        # Build base URL and base query params once
        base_url = build_request_url(
            profile.base_url, endpoint.path, endpoint.path_variables or {}
        )
        base_query_params = {
            item["key"]: item["value"] for item in (endpoint.query_params or [])
        }

        # Apply endpoint-level headers as defaults
        endpoint_header_dict = {
            item["name"]: item["value"] for item in (endpoint.endpoint_headers or [])
        }

        cumulative_page_count = 0
        cumulative_total_fetched = 0
        overall_start = time.monotonic()
        page_params = strategy.initial_params()

        while True:
            # Determine URL and params for this page
            if "_next_url" in page_params:
                # NextURL / LinkHeader sentinel — use the full URL directly
                request_url = page_params["_next_url"]
                request_params = {}
            else:
                request_url = base_url
                # Pagination params override base endpoint params on key collision
                request_params = {**base_query_params, **page_params}

            # Make request with retry
            response = self._request_with_retry(
                url=request_url,
                auth_handler=auth_handler,
                credentials=credentials,
                ssl_verify=profile.ssl_verify,
                params=request_params,
                headers=endpoint_header_dict,
                timeout=profile.request_timeout,
                safety=safety,
            )

            # Parse JSON
            try:
                body = response.json()
            except (json.JSONDecodeError, Exception) as exc:
                raise PaginationEngineError(
                    f"API returned non-JSON response at page {cumulative_page_count + 1}. "
                    f"Enable data_root_path validation or check the endpoint URL."
                ) from exc

            # Extract records
            records = extract_records_at_path(body, endpoint.data_root_path)

            # Truncate to row_limit before counting or yielding
            if row_limit is not None:
                remaining_budget = row_limit - cumulative_total_fetched
                records = records[:remaining_budget]

            cumulative_page_count += 1
            cumulative_total_fetched += len(records)

            paginated_response = PaginatedResponse(
                raw_headers=dict(response.headers),
                raw_body=body,
                records=records,
                page_count=cumulative_page_count,
                total_fetched=cumulative_total_fetched,
            )

            logger.debug(
                "PaginationEngine page=%d records=%d total_fetched=%d latency_ms=%d",
                cumulative_page_count,
                len(records),
                cumulative_total_fetched,
                int(response.elapsed.total_seconds() * 1000)
                if hasattr(response, "elapsed")
                else 0,
            )

            # Yield this page's records to the caller
            yield records

            # Check row_limit — stop if caller's row budget is exhausted
            if row_limit is not None and cumulative_total_fetched >= row_limit:
                break

            # Ask strategy for next page params
            next_page_params = strategy.next_params(paginated_response)
            if next_page_params is None:
                break

            # Check safety limits
            if strategy.is_complete(paginated_response, safety):
                break

            # Inter-page delay
            if safety.inter_page_delay_ms > 0:
                time.sleep(safety.inter_page_delay_ms / 1000)

            page_params = next_page_params

        overall_ms = int((time.monotonic() - overall_start) * 1000)
        logger.info(
            "PaginationEngine complete: pages=%d total_records=%d duration_ms=%d",
            cumulative_page_count,
            cumulative_total_fetched,
            overall_ms,
        )

    def _request_with_retry(
        self,
        url: str,
        auth_handler: BaseAuthHandler,
        credentials: dict,
        ssl_verify: bool,
        params: dict,
        headers: dict,
        timeout: int,
        safety: SafetyConfig,
    ) -> httpx.Response:
        """
        Make an authenticated GET request with exponential-backoff retry.

        Retries on: 429, 500, 502, 503, 504 (transient errors).
        Immediate re-raise on: HTTPTimeoutError, HTTPNetworkError (structural).

        Security: NEVER log request params — may contain API key in query string.
        Log retry attempts at WARNING level with URL (no query string).
        """
        url_no_qs = url.split("?")[0]
        delay_s = safety.initial_retry_delay_ms / 1000
        retryable_codes = {429, 500, 502, 503, 504}

        for attempt in range(safety.max_retries + 1):
            try:
                request = httpx.Request("GET", url, params=params, headers=headers)
                authenticated_request = auth_handler.prepare_request(
                    request, credentials
                )

                with httpx.Client(verify=ssl_verify, timeout=timeout) as client:
                    response = client.send(authenticated_request)

                if response.status_code >= 400:
                    if (
                        response.status_code in retryable_codes
                        and attempt < safety.max_retries
                    ):
                        logger.warning(
                            "PaginationEngine HTTP %s on attempt %d/%d for %s — retrying in %.1fs",
                            response.status_code,
                            attempt + 1,
                            safety.max_retries,
                            url_no_qs,
                            delay_s,
                        )
                        time.sleep(delay_s)
                        delay_s *= 2  # exponential backoff
                        continue
                    # Non-retryable or max retries exhausted
                    raise HTTPStatusError(
                        f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text[:512],
                    )

                return response

            except HTTPStatusError:
                raise
            except httpx.TimeoutException as exc:
                # Timeout is structural — immediate re-raise, no retry
                raise HTTPTimeoutError(str(exc), url=url) from exc
            except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                # Network failure is structural — immediate re-raise
                raise HTTPNetworkError(str(exc), url=url) from exc

        # Should not reach here, but satisfy return type
        raise HTTPStatusError(  # pragma: no cover
            "Max retries exhausted", status_code=0, response_body=""
        )
