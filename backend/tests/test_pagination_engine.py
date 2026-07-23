# backend/tests/test_pagination_engine.py
"""
PaginationEngine integration tests.
All HTTP calls mocked via pytest-httpx. DB needed for Endpoint model.
"""

import pytest

from api_connector.models import ResponseFormat
from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
from api_connector.services.pagination.engine import (
    PaginationEngine,
    PaginationEngineError,
)
from api_connector.services.pagination.strategies import (
    CursorStrategy,
    NextURLStrategy,
    NoPaginationStrategy,
    OffsetLimitStrategy,
    PageSizeStrategy,
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


def _xml_page(ids):
    """Build a minimal XML page body: <data><item><id>...</id></item>...</data>.
    Root tag becomes the top-level dict key (xmltodict has exactly one root),
    so data_root_path="data.item" resolves it, mirroring the JSON tests'
    {"data": [...]} shape."""
    items = "".join(f"<item><id>{i}</id></item>" for i in ids)
    return f"<data>{items}</data>".encode()


def collect_pages(engine, **kwargs):
    """Collect all pages from the engine, unpacking (records, body) tuples."""
    return [records for records, _ in engine.paginate(**kwargs)]


def _xml_page_with_meta(ids, meta_xml=""):
    """Build an XML page body: <root><data><item>...</item></data>{meta_xml}</root>.
    Parallels _xml_page, adding a <meta> sibling to the <data> root for the
    3 body-reading strategies (Cursor/NextURL/PageSize's total_pages_path)
    that read a value out of response.raw_body via get_at_path()."""
    items = "".join(f"<item><id>{i}</id></item>" for i in ids)
    return f"<root><data>{items}</data>{meta_xml}</root>".encode()


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


@pytest.mark.django_db
class TestPaginationEngineXml:
    """P2.B-01: format-aware parse branch. Zero regression on the JSON path
    (above) is the actual bar; these confirm the XML path reaches parity."""

    def test_happy_path_same_shape_as_json(self, httpx_mock):
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="data.item",
            response_format=ResponseFormat.XML,
        )
        httpx_mock.add_response(content=_xml_page([1, 2]), status_code=200)

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
        assert pages[0][0]["id"] == "1"

    def test_malformed_xml_raises_format_aware_error(self, httpx_mock):
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            response_format=ResponseFormat.XML,
        )
        httpx_mock.add_response(
            content=b"<response><data><item></response>", status_code=200
        )

        engine = PaginationEngine()
        with pytest.raises(PaginationEngineError) as exc_info:
            list(
                engine.paginate(
                    endpoint=endpoint,
                    auth_handler=NoneAuthHandler(),
                    credentials={},
                    strategy=NoPaginationStrategy(),
                    safety=SAFETY,
                )
            )
        assert "xml" in str(exc_info.value)
        assert "non-JSON" not in str(exc_info.value)

    def test_row_limit_stops_early(self, httpx_mock):
        """Mirrors the JSON row_limit test — same early-exit generator
        contract, XML-configured endpoint."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="data.item",
            response_format=ResponseFormat.XML,
        )
        strategy = OffsetLimitStrategy(OL_PARAMS)

        for _ in range(2):
            httpx_mock.add_response(content=_xml_page(range(10)), status_code=200)

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

    def test_max_pages_early_stop(self, httpx_mock):
        """Mirrors schema inference's max_pages=3 cap — generator's for/next
        early-stop behavior against an XML-configured endpoint."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="data.item",
            response_format=ResponseFormat.XML,
        )
        strategy = OffsetLimitStrategy(OL_PARAMS)
        safety = SafetyConfig(max_pages=3, max_records=10000)

        for _ in range(3):
            httpx_mock.add_response(content=_xml_page(range(10)), status_code=200)

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

        assert len(pages) == 3
        assert len(httpx_mock.get_requests()) == 3

    def test_cursor_strategy_reads_cursor_from_xml_body(self, httpx_mock):
        """P3.A-01: CursorStrategy reads meta.cursor out of the normalized
        XML body via get_at_path() — same traversal as JSON, zero strategy
        code changes. Covers both cursor-present (continues) and
        cursor-absent (stops) — mirroring TestCursorStrategy's unit
        coverage end-to-end."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="root.data.item",
            response_format=ResponseFormat.XML,
        )
        strategy = CursorStrategy(
            {
                "cursor_request_param": "after",
                "cursor_response_path": "root.meta.cursor",
            }
        )

        httpx_mock.add_response(
            content=_xml_page_with_meta([1, 2], "<meta><cursor>abc123</cursor></meta>"),
            status_code=200,
        )
        httpx_mock.add_response(
            content=_xml_page_with_meta([3, 4], "<meta></meta>"), status_code=200
        )

        engine = PaginationEngine()
        pages = collect_pages(
            engine,
            endpoint=endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=strategy,
            safety=SAFETY,
        )

        assert [len(p) for p in pages] == [2, 2]
        requests = httpx_mock.get_requests()
        assert len(requests) == 2
        assert requests[1].url.params["after"] == "abc123"

    def test_next_url_strategy_follows_next_url_from_xml_body(self, httpx_mock):
        """P3.A-01: NextURLStrategy reads links.next out of the normalized
        XML body and the engine follows the `_next_url` sentinel — zero
        strategy/engine code changes. Covers both next-url-present
        (follows) and next-url-absent (stops).

        Uses a query-string-free next_url deliberately: this test uncovered
        a pre-existing, format-agnostic bug in PaginationEngine._request_with_retry
        (engine.py:252, `req_kwargs = {"params": params, ...}` passed to
        httpx.Request unconditionally) — passing an explicit empty `params={}`
        to httpx.Request strips any query string already present in the
        `_next_url` sentinel's URL, for JSON endpoints too. Out of scope for
        this XML-support phase (not downstream of XML normalization, DEC-1);
        flagged in implementation.md §9 for separate follow-up rather than
        fixed here."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="root.data.item",
            response_format=ResponseFormat.XML,
        )
        strategy = NextURLStrategy({"next_url_response_path": "root.meta.next_url"})
        next_url = "https://api.example.com/items/page/2"

        httpx_mock.add_response(
            content=_xml_page_with_meta(
                [1, 2], f"<meta><next_url>{next_url}</next_url></meta>"
            ),
            status_code=200,
        )
        httpx_mock.add_response(
            content=_xml_page_with_meta([3, 4], "<meta></meta>"), status_code=200
        )

        engine = PaginationEngine()
        pages = collect_pages(
            engine,
            endpoint=endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=strategy,
            safety=SAFETY,
        )

        assert [len(p) for p in pages] == [2, 2]
        requests = httpx_mock.get_requests()
        assert len(requests) == 2
        assert str(requests[1].url) == next_url

    def test_page_size_strategy_total_pages_and_fallback_from_xml_body(
        self, httpx_mock
    ):
        """P3.A-01: PageSizeStrategy resolves total_pages_path from the
        normalized XML body (stops at the declared page count); when
        total_pages_path is absent, it falls back to the same record-count
        comparison OffsetLimitStrategy already uses — zero strategy code
        changes either way."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile,
            path="/items",
            data_root_path="root.data.item",
            response_format=ResponseFormat.XML,
        )
        engine = PaginationEngine()

        # Sub-case 1: total_pages_path resolved → stops at the declared page count.
        httpx_mock.add_response(
            content=_xml_page_with_meta(
                [1, 2], "<meta><total_pages>1</total_pages></meta>"
            ),
            status_code=200,
        )
        strategy_with_total = PageSizeStrategy(
            {
                "page_param": "page",
                "page_size_param": "per_page",
                "page_size": 2,
                "total_pages_path": "root.meta.total_pages",
            }
        )
        pages = collect_pages(
            engine,
            endpoint=endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=strategy_with_total,
            safety=SAFETY,
        )
        assert len(pages) == 1

        # Sub-case 2: total_pages_path absent → falls back to record-count
        # comparison (len(records) < page_size stops pagination). Uses a
        # page_size of 3 (not 2) so the terminating partial page holds 2
        # records rather than a lone singleton — a single <item> in one XML
        # document doesn't coerce to a list (DEC-8's documented residual
        # risk: list-coercion is document-local, scoped per page), which
        # would make extract_records_at_path see 0 records instead of 1 and
        # produce a false-positive stop for the wrong reason.
        httpx_mock.add_response(
            content=_xml_page_with_meta([1, 2, 3], ""), status_code=200
        )
        httpx_mock.add_response(
            content=_xml_page_with_meta([4, 5], ""), status_code=200
        )
        strategy_no_total = PageSizeStrategy(
            {"page_param": "page", "page_size_param": "per_page", "page_size": 3}
        )
        pages_fallback = collect_pages(
            engine,
            endpoint=endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=strategy_no_total,
            safety=SAFETY,
        )
        assert [len(p) for p in pages_fallback] == [3, 2]

        assert len(httpx_mock.get_requests()) == 3


@pytest.mark.django_db
class TestPaginationEngineRawResponseSink:
    """P3.B-01: raw_response_sink out-parameter — additive, format-agnostic.
    Populated regardless of endpoint.response_format; None default is a
    complete no-op (zero behavior change from Phase 2)."""

    def test_sink_populated_after_one_page(self, httpx_mock):
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        body_text = '{"data": [{"id": 1}]}'
        httpx_mock.add_response(content=body_text.encode(), status_code=200)

        engine = PaginationEngine()
        sink: dict = {}
        list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=NoPaginationStrategy(),
                safety=SAFETY,
                raw_response_sink=sink,
            )
        )

        assert sink["text"] == body_text

    def test_sink_none_default_is_a_no_op(self, httpx_mock):
        """Default (no sink passed) — no behavior change from Phase 2."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        httpx_mock.add_response(json={"data": [{"id": 1}]}, status_code=200)

        engine = PaginationEngine()
        pages = collect_pages(
            engine,
            endpoint=endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=NoPaginationStrategy(),
            safety=SAFETY,
        )
        assert pages == [[{"id": 1}]]

    def test_sink_holds_last_page_text_across_multiple_pages(self, httpx_mock):
        """Multi-page pagination: sink holds the LAST page's text once
        iteration stops, not the first page or a concatenation."""
        profile = ConnectionProfileFactory(base_url="https://api.example.com")
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        strategy = OffsetLimitStrategy(OL_PARAMS)
        page1 = '{"data": [' + ", ".join(f'{{"id": {i}}}' for i in range(10)) + "]}"
        page2 = '{"data": [{"id": 10}, {"id": 11}]}'
        httpx_mock.add_response(content=page1.encode(), status_code=200)
        httpx_mock.add_response(content=page2.encode(), status_code=200)

        engine = PaginationEngine()
        sink: dict = {}
        list(
            engine.paginate(
                endpoint=endpoint,
                auth_handler=NoneAuthHandler(),
                credentials={},
                strategy=strategy,
                safety=SAFETY,
                raw_response_sink=sink,
            )
        )

        assert sink["text"] == page2


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
