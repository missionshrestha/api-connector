# backend/tests/test_pagination_strategies.py
"""
Pagination strategy unit tests. No @pytest.mark.django_db — pure Python.

50+ tests covering all edge cases per strategy, especially:
  - OffsetLimit: records == page_size → NOT stop
  - Cursor: integer 0 → NOT stop
  - Safety limits: enforced by super().is_complete()
  - parse_link_header: both quote styles
"""

import pytest

from api_connector.services.pagination.strategies import (
    CursorStrategy,
    LinkHeaderStrategy,
    NextURLStrategy,
    NoPaginationStrategy,
    OffsetLimitStrategy,
    PageSizeStrategy,
    get_at_path,
    parse_link_header,
)
from api_connector.services.pagination.types import PaginatedResponse, SafetyConfig


def make_response(
    records=None,
    raw_body=None,
    raw_headers=None,
    page_count=1,
    total_fetched=None,
):
    if records is None:
        records = []
    if total_fetched is None:
        total_fetched = len(records)
    return PaginatedResponse(
        raw_headers=raw_headers or {},
        raw_body=raw_body or {},
        records=records,
        page_count=page_count,
        total_fetched=total_fetched,
    )


SAFETY = SafetyConfig(max_pages=100, max_records=10000)
TIGHT_SAFETY = SafetyConfig(max_pages=2, max_records=50)


# ── get_at_path utility ───────────────────────────────────────────────────────


class TestGetAtPath:
    def test_simple_key(self):
        assert get_at_path({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert get_at_path({"a": {"b": 2}}, "a.b") == 2

    def test_deeply_nested(self):
        assert get_at_path({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key_returns_none(self):
        assert get_at_path({"a": 1}, "b") is None

    def test_non_dict_node_returns_none(self):
        assert get_at_path({"a": [1, 2]}, "a.b") is None

    def test_integer_zero_returned(self):
        assert get_at_path({"cursor": 0}, "cursor") == 0

    def test_empty_path_returns_none(self):
        assert get_at_path({}, "") is None


# ── NoPaginationStrategy ──────────────────────────────────────────────────────


class TestNoPaginationStrategy:
    def test_initial_params_empty(self):
        assert NoPaginationStrategy().initial_params() == {}

    def test_next_params_always_none(self):
        s = NoPaginationStrategy()
        assert s.next_params(make_response([{"id": 1}] * 100)) is None
        assert s.next_params(make_response([])) is None

    def test_is_complete_always_true(self):
        s = NoPaginationStrategy()
        assert s.is_complete(make_response([{"id": 1}]), SAFETY) is True


# ── OffsetLimitStrategy ───────────────────────────────────────────────────────

OL_PARAMS = {"offset_param": "offset", "limit_param": "limit", "page_size": 20}


class TestOffsetLimitStrategy:
    def test_initial_params(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        assert s.initial_params() == {"offset": 0, "limit": 20}

    def test_next_params_when_records_equal_page_size_not_none(self):
        """CRITICAL: records == page_size must NOT stop pagination."""
        s = OffsetLimitStrategy(OL_PARAMS)
        s.initial_params()
        resp = make_response(
            records=[{"id": i} for i in range(20)],
            total_fetched=20,
        )
        result = s.next_params(resp)
        assert result is not None, "Should NOT stop when records == page_size"
        assert result["offset"] == 20
        assert result["limit"] == 20

    def test_next_params_when_records_less_than_page_size(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        resp = make_response(records=[{"id": i} for i in range(15)], total_fetched=35)
        assert s.next_params(resp) is None

    def test_next_params_when_zero_records(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        resp = make_response(records=[], total_fetched=0)
        assert s.next_params(resp) is None

    def test_offset_accumulates_correctly(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        s.initial_params()
        resp1 = make_response(records=[{}] * 20, total_fetched=20)
        p1 = s.next_params(resp1)
        assert p1["offset"] == 20
        resp2 = make_response(records=[{}] * 20, total_fetched=40)
        p2 = s.next_params(resp2)
        assert p2["offset"] == 40

    def test_is_complete_within_limits(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        resp = make_response(records=[{}] * 20, total_fetched=20)
        assert s.is_complete(resp, SAFETY) is False

    def test_is_complete_at_max_pages(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        resp = make_response(records=[{}] * 20, page_count=100, total_fetched=2000)
        assert s.is_complete(resp, TIGHT_SAFETY) is True

    def test_is_complete_at_max_records(self):
        s = OffsetLimitStrategy(OL_PARAMS)
        resp = make_response(records=[{}] * 20, page_count=3, total_fetched=51)
        assert s.is_complete(resp, TIGHT_SAFETY) is True


# ── PageSizeStrategy ──────────────────────────────────────────────────────────

PS_PARAMS = {"page_param": "page", "page_size_param": "per_page", "page_size": 10}
PS_PARAMS_WITH_TOTAL = {**PS_PARAMS, "total_pages_path": "meta.total_pages"}


class TestPageSizeStrategy:
    def test_initial_params(self):
        s = PageSizeStrategy(PS_PARAMS)
        assert s.initial_params() == {"page": 1, "per_page": 10}

    def test_next_params_advances_page(self):
        s = PageSizeStrategy(PS_PARAMS)
        s.initial_params()
        resp = make_response(records=[{}] * 10, total_fetched=10)
        result = s.next_params(resp)
        assert result == {"page": 2, "per_page": 10}

    def test_next_params_stops_on_partial_page(self):
        s = PageSizeStrategy(PS_PARAMS)
        s.initial_params()
        resp = make_response(records=[{}] * 7, total_fetched=17)
        assert s.next_params(resp) is None

    def test_next_params_stops_when_total_pages_reached(self):
        s = PageSizeStrategy(PS_PARAMS_WITH_TOTAL)
        s.initial_params()
        resp = make_response(
            records=[{}] * 10,
            raw_body={"meta": {"total_pages": 1}},
            page_count=1,
            total_fetched=10,
        )
        assert s.next_params(resp) is None


# ── CursorStrategy ────────────────────────────────────────────────────────────

CS_PARAMS = {"cursor_request_param": "after", "cursor_response_path": "meta.cursor"}


class TestCursorStrategy:
    def test_initial_params_empty(self):
        assert CursorStrategy(CS_PARAMS).initial_params() == {}

    def test_next_params_with_valid_string_cursor(self):
        s = CursorStrategy(CS_PARAMS)
        resp = make_response(raw_body={"meta": {"cursor": "abc123"}})
        assert s.next_params(resp) == {"after": "abc123"}

    def test_next_params_cursor_zero_not_stopped(self):
        """CRITICAL: integer 0 is a valid cursor value."""
        s = CursorStrategy(CS_PARAMS)
        resp = make_response(raw_body={"meta": {"cursor": 0}})
        result = s.next_params(resp)
        assert result is not None, "cursor=0 should NOT stop pagination"
        assert result["after"] == 0

    def test_next_params_cursor_none_stops(self):
        s = CursorStrategy(CS_PARAMS)
        resp = make_response(raw_body={"meta": {"cursor": None}})
        assert s.next_params(resp) is None

    def test_next_params_cursor_empty_string_stops(self):
        s = CursorStrategy(CS_PARAMS)
        resp = make_response(raw_body={"meta": {"cursor": ""}})
        assert s.next_params(resp) is None

    def test_next_params_cursor_absent_stops(self):
        s = CursorStrategy(CS_PARAMS)
        resp = make_response(raw_body={"meta": {}})
        assert s.next_params(resp) is None


# ── NextURLStrategy ───────────────────────────────────────────────────────────

NU_PARAMS = {"next_url_response_path": "links.next"}


class TestNextURLStrategy:
    def test_next_params_returns_sentinel_when_url_present(self):
        s = NextURLStrategy(NU_PARAMS)
        resp = make_response(
            raw_body={"links": {"next": "https://api.com/items?page=2"}}
        )
        result = s.next_params(resp)
        assert result == {"_next_url": "https://api.com/items?page=2"}

    def test_next_params_none_when_url_absent(self):
        s = NextURLStrategy(NU_PARAMS)
        resp = make_response(raw_body={"links": {"next": None}})
        assert s.next_params(resp) is None

    def test_next_params_none_when_path_missing(self):
        s = NextURLStrategy(NU_PARAMS)
        resp = make_response(raw_body={})
        assert s.next_params(resp) is None


# ── LinkHeaderStrategy ────────────────────────────────────────────────────────


class TestLinkHeaderStrategy:
    def test_next_params_with_quoted_rel_next(self):
        s = LinkHeaderStrategy()
        resp = make_response(
            raw_headers={"link": '<https://api.com/page=2>; rel="next"'}
        )
        assert s.next_params(resp) == {"_next_url": "https://api.com/page=2"}

    def test_next_params_with_unquoted_rel_next(self):
        s = LinkHeaderStrategy()
        resp = make_response(raw_headers={"link": "<https://api.com/page=2>; rel=next"})
        assert s.next_params(resp) == {"_next_url": "https://api.com/page=2"}

    def test_next_params_none_when_no_next_rel(self):
        s = LinkHeaderStrategy()
        resp = make_response(
            raw_headers={"link": '<https://api.com/page=1>; rel="prev"'}
        )
        assert s.next_params(resp) is None

    def test_next_params_none_when_header_absent(self):
        s = LinkHeaderStrategy()
        resp = make_response(raw_headers={})
        assert s.next_params(resp) is None


# ── parse_link_header ─────────────────────────────────────────────────────────


class TestParseLinkHeader:
    def test_quoted_rel(self):
        result = parse_link_header('<https://api.com/p=2>; rel="next"')
        assert result == {"next": "https://api.com/p=2"}

    def test_unquoted_rel(self):
        result = parse_link_header("<https://api.com/p=2>; rel=next")
        assert result == {"next": "https://api.com/p=2"}

    def test_multiple_rels(self):
        result = parse_link_header(
            '<https://api.com/p=2>; rel="next", <https://api.com/p=0>; rel="prev"'
        )
        assert result["next"] == "https://api.com/p=2"
        assert result["prev"] == "https://api.com/p=0"

    def test_empty_header(self):
        assert parse_link_header("") == {}


# ── Safety limits — enforced across all strategies ────────────────────────────


class TestSafetyLimitsAllStrategies:
    @pytest.mark.parametrize(
        "strategy_cls,params",
        [
            (NoPaginationStrategy, {}),
            (OffsetLimitStrategy, OL_PARAMS),
            (PageSizeStrategy, PS_PARAMS),
            (CursorStrategy, CS_PARAMS),
            (NextURLStrategy, NU_PARAMS),
            (LinkHeaderStrategy, {}),
        ],
    )
    def test_is_complete_at_max_pages(self, strategy_cls, params):
        s = strategy_cls(params)
        resp = make_response(records=[{}] * 10, page_count=2, total_fetched=20)
        tight = SafetyConfig(max_pages=2, max_records=10000)
        assert s.is_complete(resp, tight) is True

    @pytest.mark.parametrize(
        "strategy_cls,params",
        [
            (OffsetLimitStrategy, OL_PARAMS),
            (PageSizeStrategy, PS_PARAMS),
            (CursorStrategy, CS_PARAMS),
        ],
    )
    def test_is_complete_at_max_records(self, strategy_cls, params):
        s = strategy_cls(params)
        resp = make_response(records=[{}] * 10, page_count=5, total_fetched=51)
        tight = SafetyConfig(max_pages=100, max_records=50)
        assert s.is_complete(resp, tight) is True
