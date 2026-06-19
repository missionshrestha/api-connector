# backend/api_connector/services/pagination/registry.py
from api_connector.services.pagination.base import BasePaginationStrategy


class PaginationRegistry:
    """
    Maps PaginationStrategy enum values to concrete BasePaginationStrategy subclasses.

    Initially empty — strategies are registered in Phase 5.
    get() raises ValueError for any lookup until Phase 5 registers them.
    """

    _registry: dict = {}

    def get(self, strategy: str) -> BasePaginationStrategy:
        handler_class = self._registry.get(strategy)
        if handler_class is None:
            raise ValueError(
                f"No strategy registered for: {strategy!r}. "
                "Pagination strategies are registered in Phase 5."
            )
        return handler_class()


# Module-level singleton
pagination_registry = PaginationRegistry()
