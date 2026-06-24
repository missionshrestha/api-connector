# backend/api_connector/services/pagination/registry.py
from api_connector.services.pagination.base import BasePaginationStrategy
from api_connector.services.pagination.strategies import (
    CursorStrategy,
    LinkHeaderStrategy,
    NextURLStrategy,
    NoPaginationStrategy,
    OffsetLimitStrategy,
    PageSizeStrategy,
)


class PaginationRegistry:
    """
    Maps PaginationStrategy enum values to concrete BasePaginationStrategy subclasses.

    After Phase 5: all 6 strategies registered.
    get() accepts params dict — passed to strategy constructor.
    Each call returns a new instance (strategies track per-run state).
    """

    _registry: dict[str, type[BasePaginationStrategy]] = {
        "no_pagination": NoPaginationStrategy,
        "offset_limit": OffsetLimitStrategy,
        "page_size": PageSizeStrategy,
        "cursor": CursorStrategy,
        "next_url": NextURLStrategy,
        "link_header": LinkHeaderStrategy,
    }

    def get(self, strategy: str, params: dict | None = None) -> BasePaginationStrategy:
        """
        Instantiate a strategy handler for the given strategy value.

        Args:
            strategy: PaginationStrategy value string (e.g. "offset_limit").
            params: strategy_params dict from PaginationConfig. MUST be passed
                    for parametric strategies (offset_limit, page_size, cursor,
                    next_url). Passing None or {} produces KeyError on first call.

        Raises:
            ValueError: if strategy is not registered.
        """
        handler_class = self._registry.get(strategy)
        if handler_class is None:
            raise ValueError(
                f"No strategy registered for: {strategy!r}. "
                f"Valid strategies: {list(self._registry.keys())}"
            )
        return handler_class(params=params or {})


# Module-level singleton
pagination_registry = PaginationRegistry()
