# backend/api_connector/services/pagination/base.py
from abc import ABC, abstractmethod

from api_connector.services.pagination.types import PaginatedResponse, SafetyConfig


class BasePaginationStrategy(ABC):
    """
    Abstract base for all pagination strategies.

    Subclass contract:
    - initial_params(): return params for the FIRST page request.
    - next_params(): return params for the NEXT page, or None to stop.
    - is_complete(): return True if iteration should stop.

    Safety enforcement:
    The base is_complete() checks max_pages and max_records unconditionally.
    Subclasses MUST call super().is_complete() or replicate these checks.
    A strategy that overrides is_complete() without safety checks bypasses
    the engine's runaway-protection guarantee.
    """

    @abstractmethod
    def initial_params(self) -> dict:
        """Return query params / body modifications for the first request."""

    @abstractmethod
    def next_params(self, response: PaginatedResponse) -> dict | None:
        """
        Return params for the next page, or None if pagination is complete.
        None signals the PaginationEngine to stop iterating.
        """

    @abstractmethod
    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        """
        Return True if iteration should stop based on response content or safety limits.

        Base implementation enforces safety hard stops — subclasses must call super().
        Called after next_params() returns a non-None value.
        """
        return (
            response.page_count >= safety.max_pages
            or response.total_fetched >= safety.max_records
        )
