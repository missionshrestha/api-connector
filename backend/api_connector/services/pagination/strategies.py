# backend/api_connector/services/pagination/strategies.py
"""
Concrete pagination strategy implementations.

CRITICAL EDGE CASES:
  OffsetLimit: stop when len(records) < page_size (NOT <=).
    When records == page_size, make one more request to discover the end.
    Stopping at equality silently drops the last page when total_records % page_size == 0.

  Cursor: stop when cursor is None or "" (NOT when cursor == 0).
    Integer zero is a valid cursor value. Use `if cursor is None or cursor == ""`
    NOT `if not cursor` (which evaluates 0 as falsy).

  NextURL / LinkHeader: return {"_next_url": url} sentinel.
    Engine detects this key and replaces the full request URL.
"""

import re

from api_connector.services.pagination.base import BasePaginationStrategy
from api_connector.services.pagination.types import PaginatedResponse, SafetyConfig


def get_at_path(data: dict, dot_path: str):
    """
    Navigate a dot-notation path through nested dicts.
    Returns None on any traversal failure (missing key, non-dict node).
    Never raises — callers treat None as "value absent".
    """
    if not dot_path:
        return None
    parts = dot_path.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


class NoPaginationStrategy(BasePaginationStrategy):
    """
    Single-page strategy. Makes one request, yields one batch, stops.
    Used for APIs that return all records in one response.
    """

    def __init__(self, params=None):
        self.params = params or {}

    def initial_params(self) -> dict:
        return {}

    def next_params(self, response: PaginatedResponse) -> dict | None:
        return None  # Always stop after one page

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        return super().is_complete(response, safety) or True


class OffsetLimitStrategy(BasePaginationStrategy):
    """
    Standard offset/limit pagination (LIMIT/OFFSET in SQL terminology).

    Stop condition: len(records) < page_size (ONLY).
    When len(records) == page_size, we MUST make one more request.
    That extra request returns 0 records, triggering the stop condition.
    This is correct RFC behavior and cannot be optimized away.
    """

    def __init__(self, params=None):
        self.params = params or {}

    def initial_params(self) -> dict:
        return {
            self.params["offset_param"]: 0,
            self.params["limit_param"]: self.params["page_size"],
        }

    def next_params(self, response: PaginatedResponse) -> dict | None:
        # Stop ONLY when records < page_size (last page was partial or empty)
        if len(response.records) < self.params["page_size"]:
            return None
        # response.total_fetched is cumulative AFTER this page — use as next offset
        return {
            self.params["offset_param"]: response.total_fetched,
            self.params["limit_param"]: self.params["page_size"],
        }

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        return len(response.records) < self.params["page_size"] or super().is_complete(
            response, safety
        )


class PageSizeStrategy(BasePaginationStrategy):
    """
    Page number + page size pagination.

    Can optionally use total_pages_path to read the total page count
    from the response body. Falls back to record count comparison.
    """

    def __init__(self, params=None):
        self.params = params or {}
        self._current_page = 1

    def initial_params(self) -> dict:
        self._current_page = 1
        return {
            self.params["page_param"]: 1,
            self.params["page_size_param"]: self.params["page_size"],
        }

    def next_params(self, response: PaginatedResponse) -> dict | None:
        total_pages_path = self.params.get("total_pages_path")
        if total_pages_path:
            total_pages = get_at_path(response.raw_body, total_pages_path)
            if total_pages is not None:
                try:
                    if self._current_page >= int(total_pages):
                        return None
                except (TypeError, ValueError):
                    pass  # Fall through to record-count check

        if len(response.records) < self.params["page_size"]:
            return None

        self._current_page += 1
        return {
            self.params["page_param"]: self._current_page,
            self.params["page_size_param"]: self.params["page_size"],
        }

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        total_pages_path = self.params.get("total_pages_path")
        if total_pages_path:
            total_pages = get_at_path(response.raw_body, total_pages_path)
            if total_pages is not None:
                try:
                    if self._current_page >= int(total_pages):
                        return True
                except (TypeError, ValueError):
                    pass

        return len(response.records) < self.params["page_size"] or super().is_complete(
            response, safety
        )


def parse_link_header(header_value: str) -> dict[str, str]:
    """
    Parse RFC 5988 Link header into {rel: url} dict.
    Supports both rel="next" and rel=next formats.

    Example:
        '<https://api.example.com/items?page=2>; rel="next"'
        → {'next': 'https://api.example.com/items?page=2'}
    """
    pattern = r'<([^>]+)>;\s*rel=["\']?([^"\',\s]+)["\']?'
    return {rel: url for url, rel in re.findall(pattern, header_value)}


class CursorStrategy(BasePaginationStrategy):
    """
    Cursor-based pagination. Reads cursor from response body.

    CRITICAL: cursor == 0 (integer zero) IS a valid cursor value.
    Use `cursor is None or cursor == ""` NOT `not cursor`.
    """

    def __init__(self, params=None):
        self.params = params or {}

    def initial_params(self) -> dict:
        return {}

    def next_params(self, response: PaginatedResponse) -> dict | None:
        cursor = get_at_path(response.raw_body, self.params["cursor_response_path"])
        # integer 0 is a valid cursor — only None and "" mean "no more pages"
        if cursor is None or cursor == "":
            return None
        return {self.params["cursor_request_param"]: cursor}

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        return super().is_complete(response, safety)


class NextURLStrategy(BasePaginationStrategy):
    """
    Next URL from response body. The engine detects the _next_url sentinel
    and replaces the entire request URL for the next page.
    """

    def __init__(self, params=None):
        self.params = params or {}

    def initial_params(self) -> dict:
        return {}

    def next_params(self, response: PaginatedResponse) -> dict | None:
        next_url = get_at_path(response.raw_body, self.params["next_url_response_path"])
        if not next_url:
            return None
        # Sentinel: engine replaces the full URL instead of merging as query param
        return {"_next_url": next_url}

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        return super().is_complete(response, safety)


class LinkHeaderStrategy(BasePaginationStrategy):
    """
    RFC 5988 Link header pagination. Reads rel="next" URL from the response
    Link header, then uses the _next_url sentinel for the engine to follow.
    """

    def __init__(self, params=None):
        self.params = params or {}

    def initial_params(self) -> dict:
        return {}

    def next_params(self, response: PaginatedResponse) -> dict | None:
        link_header = response.raw_headers.get("link", "")
        rels = parse_link_header(link_header)
        next_url = rels.get("next")
        if not next_url:
            return None
        return {"_next_url": next_url}

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        return super().is_complete(response, safety)
