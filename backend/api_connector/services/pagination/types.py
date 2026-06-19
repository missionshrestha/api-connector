# backend/api_connector/services/pagination/types.py
from dataclasses import dataclass


@dataclass
class PaginatedResponse:
    """
    Carries the result of one page fetch plus cumulative counters.

    page_count and total_fetched are cumulative — maintained by the PaginationEngine
    and passed into each is_complete() call. Without them, a strategy cannot enforce
    max_pages safety (it would only know the current page's record count, not how
    many pages have already run).
    """

    raw_headers: dict  # Response headers as a dict
    raw_body: dict  # Parsed response body
    records: list  # Records extracted from data_root_path
    page_count: int  # How many pages fetched so far (cumulative)
    total_fetched: int  # How many records fetched so far (cumulative)


@dataclass
class SafetyConfig:
    """
    Unconditional hard-stop limits for the PaginationEngine.

    These are not suggestions. Phase 5's PaginationEngine must enforce them
    regardless of what a strategy's next_params() returns.
    """

    max_pages: int = 100
    max_records: int = 10000
    inter_page_delay_ms: int = 0
    max_retries: int = 3
    initial_retry_delay_ms: int = 1000
