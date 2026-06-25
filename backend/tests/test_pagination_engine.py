# backend/tests/test_pagination_engine.py
"""
PaginationEngine integration tests.
All HTTP calls mocked via pytest-httpx. DB needed for Endpoint model.
"""

import pytest

from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
from api_connector.services.pagination.engine import (
    PaginationEngine,
    PaginationEngineError,
)
from api_connector.services.pagination.strategies import (
    NoPaginationStrategy,
    OffsetLimitStrategy,
)
from api_connector.services.pagination.types import SafetyConfig
from api_connector.services.pagination.utils import (
    build_request_url,
    detect_data_root,
    extract_records_at_path,
)
from tests.factories import (
    ConnectionProfileFactory,
    EndpointFactory,
)

SAFETY = SafetyConfig(max_pages=100, max_records=10000)
OL_PARAMS = {"offset_param": "offset", "limit_param": "limit", "page_size": 10}


def collect_pages(engine, **kwargs):
    """Collect all pages from the engine, unpacking (records, body) tuples."""
    return [records for records, _ in engine.paginate(**kwargs)]


@pytest.mark.django_db
class TestPaginationEngineOffsetLimit:
    def test_happy_path_three_pages(self, httpx_mock):
        """Three pages: 10, 10, 5 records. Total = 25, 3 yields."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        strategy = OffsetLimitStrategy(OL_PARAMS)

        httpx_mock.add_response(
            json={"data": [{"id": i} for i in range(10)]}, status_code=200
        )
        httpx_mock.add_response(
            json={"data": [{"id": i} for i in range(10, 20)]}, status_code=200
        )
        httpx_mock.add_response(
            json={"data": [{"id": i} for i in range(20, 25)]}, status_code=200
        )

        engine = PaginationEngine()
        raw_results = list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=strategy,
                safety=SAFETY,
            )
        )
        pages = [records for records, _ in raw_results]

        assert len(pages) == 3
        assert len(pages[0]) == 10
        assert len(pages[1]) == 10
        assert len(pages[2]) == 5
        total = sum(len(p) for p in pages)
        assert total == 25

    def test_row_limit_stops_early(self, httpx_mock):
        """row_limit=15 stops after page 2 (10+5 = 15 ≤ 15)."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        strategy = OffsetLimitStrategy(OL_PARAMS)

        # Register exactly 2 — if engine fetches a 3rd, pytest_httpx raises immediately
        for _ in range(2):
            httpx_mock.add_response(
                json={"data": [{"id": i} for i in range(10)]}, status_code=200
            )

        engine = PaginationEngine()
        raw_results = list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=strategy,
                safety=SAFETY,
                row_limit=15,
            )
        )
        pages = [records for records, _ in raw_results]

        total = sum(len(p) for p in pages)
        assert total <= 15
        assert len(httpx_mock.get_requests()) == 2

    def test_no_pagination_yields_exactly_once(self, httpx_mock):
        """NoPaginationStrategy: exactly one yield."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path=None
        )
        httpx_mock.add_response(json=[{"id": 1}, {"id": 2}], status_code=200)

        engine = PaginationEngine()

        raw_results = list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=NoPaginationStrategy(),
                safety=SAFETY,
            )
        )
        pages = [records for records, _ in raw_results]

        assert len(pages) == 1
        assert len(pages[0]) == 2

    def test_non_json_response_raises_engine_error(self, httpx_mock):
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        httpx_mock.add_response(text="Not JSON", status_code=200)

        engine = PaginationEngine()
        with pytest.raises(PaginationEngineError):
            list(
                engine.paginate(
                    endpoint=endpoint,
                    auth_handler=NoneAuthHandler(),
                    credentials={},
                    strategy=NoPaginationStrategy(),
                    safety=SAFETY,
                )
            )

    def test_retry_on_429_then_success(self, httpx_mock):
        """Two 429s then 200 — engine recovers and continues."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        strategy = NoPaginationStrategy()

        httpx_mock.add_response(status_code=429, text="Rate limited")
        httpx_mock.add_response(status_code=429, text="Rate limited")
        httpx_mock.add_response(json={"data": [{"id": 1}]}, status_code=200)

        safety = SafetyConfig(
            max_pages=100, max_records=10000, max_retries=3, initial_retry_delay_ms=0
        )
        engine = PaginationEngine()

        raw_results = list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=strategy,
                safety=safety,
            )
        )
        pages = [records for records, _ in raw_results]

        assert len(pages) == 1
        assert pages[0] == [{"id": 1}]

    def test_data_root_path_extraction(self, httpx_mock):
        """data_root_path correctly navigates nested response."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="response.data.items",
        )
        httpx_mock.add_response(
            json={"response": {"data": {"items": [{"id": 1}]}}},
            status_code=200,
        )
        engine = PaginationEngine()

        raw_results = list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=NoPaginationStrategy(),
                safety=SAFETY,
            )
        )
        pages = [records for records, _ in raw_results]

        assert pages == [[{"id": 1}]]


# ── detect_data_root unit tests ───────────────────────────────────────────────


class TestDetectDataRoot:
    def test_top_level_array_of_dicts(self):
        result = detect_data_root({"data": [{"id": 1}], "meta": {"total": 1}})
        assert result == ["data"]

    def test_nested_array(self):
        result = detect_data_root({"outer": {"inner": [{"id": 1}]}})
        assert result == ["outer.inner"]

    def test_shallowest_first(self):
        result = detect_data_root(
            {"flat": [{"id": 2}], "outer": {"inner": [{"id": 1}]}}
        )
        assert result[0] == "flat"

    def test_larger_array_preferred_at_same_depth(self):
        result = detect_data_root(
            {
                "small": [{"id": 1}],
                "large": [{"id": i} for i in range(10)],
            }
        )
        assert result[0] == "large"

    def test_empty_list_not_candidate(self):
        result = detect_data_root({"data": [], "meta": {"total": 0}})
        assert result == []

    def test_list_of_non_dicts_not_candidate(self):
        result = detect_data_root({"ids": [1, 2, 3]})
        assert result == []

    def test_root_list_returns_empty(self):
        """Root-level list has no path."""
        result = detect_data_root([{"id": 1}])
        assert result == []

    def test_multiple_candidates_ordered(self):
        result = detect_data_root(
            {
                "data": [{"id": 1}],
                "nested": {"items": [{"id": 2}]},
            }
        )
        assert result == ["data", "nested.items"]


# ── extract_records_at_path unit tests ───────────────────────────────────────


class TestExtractRecordsAtPath:
    def test_nested_path(self):
        assert extract_records_at_path(
            {"data": {"items": [{"id": 1}]}}, "data.items"
        ) == [{"id": 1}]

    def test_root_list_no_path(self):
        assert extract_records_at_path([{"id": 1}], None) == [{"id": 1}]

    def test_wrong_path_returns_empty(self):
        assert extract_records_at_path({"data": [{"id": 1}]}, "wrong.path") == []

    def test_none_input_returns_empty(self):
        assert extract_records_at_path(None, "data") == []

    def test_non_list_at_path_returns_empty(self):
        assert extract_records_at_path({"data": "not a list"}, "data") == []


# ── build_request_url unit tests ──────────────────────────────────────────────


class TestBuildRequestUrl:
    def test_variable_substitution(self):
        url = build_request_url(
            "https://api.example.com", "/users/{user_id}", {"user_id": "42"}
        )
        assert url == "https://api.example.com/users/42"

    def test_no_variables(self):
        url = build_request_url("https://api.example.com", "/items", {})
        assert url == "https://api.example.com/items"

    def test_unresolved_placeholder_left_as_is(self):
        url = build_request_url("https://api.com", "/users/{user_id}", {})
        assert "{user_id}" in url

    def test_trailing_slash_stripped_from_base(self):
        url = build_request_url("https://api.com/", "/items", {})
        assert url == "https://api.com/items"
