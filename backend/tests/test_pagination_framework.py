# backend/tests/test_pagination_framework.py
"""
Pagination framework tests. NO @pytest.mark.django_db needed.
Pure Python — no DB access, no Django ORM.
"""

import pytest

from api_connector.services.pagination.base import BasePaginationStrategy
from api_connector.services.pagination.registry import pagination_registry
from api_connector.services.pagination.types import PaginatedResponse, SafetyConfig

# ── Minimal concrete stub for testing base class behavior ─────────────────────


class _StubStrategy(BasePaginationStrategy):
    def initial_params(self) -> dict:
        return {}

    def next_params(self, response: PaginatedResponse) -> dict | None:
        return None

    def is_complete(self, response: PaginatedResponse, safety: SafetyConfig) -> bool:
        return super().is_complete(response, safety)


def make_response(page_count: int, total_fetched: int) -> PaginatedResponse:
    return PaginatedResponse(
        raw_headers={},
        raw_body={},
        records=[],
        page_count=page_count,
        total_fetched=total_fetched,
    )


# ── Dataclass instantiation ───────────────────────────────────────────────────


def test_paginated_response_requires_all_fields():
    r = make_response(page_count=1, total_fetched=100)
    assert r.page_count == 1
    assert r.total_fetched == 100
    assert r.records == []


def test_safety_config_defaults():
    s = SafetyConfig()
    assert s.max_pages == 100
    assert s.max_records == 10000
    assert s.inter_page_delay_ms == 0
    assert s.max_retries == 3
    assert s.initial_retry_delay_ms == 1000


# ── Abstractness ──────────────────────────────────────────────────────────────


def test_base_strategy_is_abstract():
    with pytest.raises(TypeError):
        BasePaginationStrategy()  # type: ignore[abstract]


# ── Safety limit enforcement ──────────────────────────────────────────────────


def test_is_complete_within_limits():
    strategy = _StubStrategy()
    response = make_response(page_count=5, total_fetched=500)
    safety = SafetyConfig(max_pages=10, max_records=1000)
    assert strategy.is_complete(response, safety) is False


def test_is_complete_at_max_pages():
    strategy = _StubStrategy()
    response = make_response(page_count=10, total_fetched=500)
    safety = SafetyConfig(max_pages=10, max_records=1000)
    assert strategy.is_complete(response, safety) is True


def test_is_complete_at_max_records():
    strategy = _StubStrategy()
    response = make_response(page_count=5, total_fetched=1000)
    safety = SafetyConfig(max_pages=10, max_records=1000)
    assert strategy.is_complete(response, safety) is True


def test_is_complete_exceeds_both_limits():
    strategy = _StubStrategy()
    response = make_response(page_count=200, total_fetched=50000)
    safety = SafetyConfig(max_pages=100, max_records=10000)
    assert strategy.is_complete(response, safety) is True


# ── Registry ──────────────────────────────────────────────────────────────────


def test_registry_resolves_all_registered_strategies():
    """
    After Phase 5: all 6 strategies must resolve without ValueError.
    This replaces the pre-Phase-5 test that asserted ValueError for all strategies.
    """
    from api_connector.models import PaginationStrategy

    dummy_params = {
        "offset_param": "offset",
        "limit_param": "limit",
        "page_size": 10,
        "page_param": "page",
        "page_size_param": "per_page",
        "cursor_request_param": "after",
        "cursor_response_path": "meta.cursor",
        "next_url_response_path": "links.next",
    }
    for strategy_value in PaginationStrategy.values:
        handler = pagination_registry.get(strategy_value, params=dummy_params)
        assert handler is not None, f"Registry returned None for {strategy_value}"
    print("All 6 strategies registered: PASS")


def test_registry_raises_for_unknown_strategy():
    with pytest.raises(ValueError):
        pagination_registry.get("completely_invalid")
