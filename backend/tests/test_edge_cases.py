# backend/tests/test_edge_cases.py
"""
Phase 8 edge case integration tests.

Covers the 7 scenarios most likely to cause issues in real-world API integration:
  1. Empty API response → 422 not 500
  2. Non-JSON API response → 400 not 500 (both inference and preview)
  3. OffsetLimit exact page_size last page → engine makes 2 requests, not 1
  4. OAuth AC refresh revoked → structured 401, not 500
  5. Cursor absent from response body → generator stops cleanly
  6. Invalid data_root_path → preview returns 200 with empty rows, not 500
  7. (Frontend) 250+ fields in SchemaExplorer → ≤ 30 DOM nodes (see dom test file)

All HTTP calls mocked — zero real outbound requests.
Engine yields (records, body) tuples per P7.A-01.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from api_connector.models import AuthType, TokenType
from api_connector.services.encryption import encryption_service
from api_connector.services.pagination.engine import PaginationEngineError
from api_connector.services.pagination.strategies import (
    CursorStrategy,
    OffsetLimitStrategy,
)
from api_connector.services.pagination.types import PaginatedResponse, SafetyConfig
from tests.factories import (
    AuthConfigFactory,
    ConnectionProfileFactory,
    EndpointFactory,
    OAuthTokenFactory,
    SchemaFieldFactory,
)

# ── Helper: make_engine_pages ─────────────────────────────────────────────────


def make_engine_gen(pages_with_bodies):
    """Return a callable that yields (records, body) tuples — matches P7.A-01 engine."""

    def _gen(*args, **kwargs):
        yield from pages_with_bodies

    return _gen


def make_profile_endpoint(auth_type="none"):
    profile = ConnectionProfileFactory(auth_type=auth_type)
    AuthConfigFactory(
        connection_profile=profile,
        encrypted_credentials=encryption_service.encrypt_dict({}),
    )
    endpoint = EndpointFactory(connection_profile=profile, path="/items")
    return profile, endpoint


# ── Edge Case 1: Empty API Response ──────────────────────────────────────────


@pytest.mark.django_db
class TestEmptyApiResponse:
    """
    When the API returns a valid JSON response with zero records,
    schema inference must return 422 (not 500) with API_CONN_051.
    No SchemaField records should be created.
    """

    def test_empty_records_returns_422(self, api_client, assert_no_credential_leak):
        profile, endpoint = make_profile_endpoint()

        with patch("api_connector.views.endpoint.SchemaInferenceEngine") as mock_cls:
            from api_connector.services.schema_inference.types import (
                SchemaInferenceNoRecordsError,
            )

            mock_engine = MagicMock()
            mock_engine.infer.side_effect = SchemaInferenceNoRecordsError(
                "No records found. Verify the data_root_path is correct."
            )
            mock_cls.return_value = mock_engine

            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/schema/infer/",
                data={},
                format="json",
            )

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        assert response.data["error_code"] == "API_CONN_051"
        assert_no_credential_leak(response)

    def test_empty_records_creates_no_schema_fields(self, api_client):
        from api_connector.models import SchemaField

        profile, endpoint = make_profile_endpoint()
        initial_count = SchemaField.objects.filter(endpoint=endpoint).count()

        with patch("api_connector.views.endpoint.SchemaInferenceEngine") as mock_cls:
            from api_connector.services.schema_inference.types import (
                SchemaInferenceNoRecordsError,
            )

            mock_cls.return_value.infer.side_effect = SchemaInferenceNoRecordsError(
                "No records"
            )

            api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/schema/infer/",
                data={},
                format="json",
            )

        assert SchemaField.objects.filter(endpoint=endpoint).count() == initial_count


# ── Edge Case 2: Non-JSON API Response ───────────────────────────────────────


@pytest.mark.django_db
class TestNonJsonResponse:
    """
    A non-JSON API response (HTML login page, XML, plain text) must return
    structured 400 errors — not 500 — from both inference and preview.
    """

    def test_inference_non_json_returns_400(
        self, api_client, assert_no_credential_leak
    ):
        profile, endpoint = make_profile_endpoint()

        with patch("api_connector.views.endpoint.SchemaInferenceEngine") as mock_cls:
            from api_connector.services.schema_inference.types import (
                SchemaInferenceError,
            )

            mock_cls.return_value.infer.side_effect = SchemaInferenceError(
                "API returned non-JSON response at page 1. Verify endpoint URL is correct."
            )

            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/schema/infer/",
                data={},
                format="json",
            )

        assert response.status_code == 400, (
            f"Expected 400 (not 500), got {response.status_code}"
        )
        assert response.data["error_code"] == "API_CONN_050"
        assert "500" not in str(response.status_code)
        assert_no_credential_leak(response)

    def test_preview_pagination_engine_error_returns_400(
        self, api_client, assert_no_credential_leak
    ):
        """
        PaginationEngineError (e.g., JSON parse failure) must return 400 from preview,
        not 500. This verifies the P8.C-02 fix is in place.
        """
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(
            endpoint=endpoint, key_path="id", include=True, inferred_type="integer"
        )

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.preview.side_effect = PaginationEngineError(
                "API returned non-JSON response at page 1."
            )
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/preview/",
                data={"row_limit": 25},
                format="json",
            )

        assert response.status_code == 400, (
            f"Expected 400 (not 500), got {response.status_code}"
        )
        assert response.data["error_code"] == "API_CONN_053"
        assert_no_credential_leak(response)

    def test_inference_error_message_no_exception_class_name(self, api_client):
        profile, endpoint = make_profile_endpoint()

        with patch("api_connector.views.endpoint.SchemaInferenceEngine") as mock_cls:
            from api_connector.services.schema_inference.types import (
                SchemaInferenceError,
            )

            mock_cls.return_value.infer.side_effect = SchemaInferenceError(
                "API returned non-JSON response at page 1."
            )

            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/schema/infer/",
                data={},
                format="json",
            )

        # CRITICAL: exception class names must not appear in user-facing messages
        assert "SchemaInferenceError" not in str(response.data)
        assert "Exception" not in str(response.data)


# ── Edge Case 3: OffsetLimit Exact page_size on Last Page ────────────────────


class TestOffsetLimitExactPageSize:
    """
    When the last page returns EXACTLY page_size records, the engine must
    make one more request (which returns 0 records) before stopping.
    Stopping at == page_size silently drops data when total_records % page_size == 0.
    """

    OL_PARAMS = {"offset_param": "offset", "limit_param": "limit", "page_size": 20}

    def test_next_params_continues_when_records_equal_page_size(self):
        strategy = OffsetLimitStrategy(self.OL_PARAMS)
        strategy.initial_params()

        # Simulate: page 1 returns exactly 20 records
        resp = PaginatedResponse(
            raw_headers={},
            raw_body={},
            records=[{"id": i} for i in range(20)],
            page_count=1,
            total_fetched=20,
        )
        result = strategy.next_params(resp)

        assert result is not None, (
            "CRITICAL BUG: OffsetLimitStrategy stopped at == page_size. "
            "This silently drops records when total_records % page_size == 0."
        )
        assert result["offset"] == 20

    def test_next_params_stops_when_records_less_than_page_size(self):
        strategy = OffsetLimitStrategy(self.OL_PARAMS)
        strategy.initial_params()

        resp = PaginatedResponse(
            raw_headers={},
            raw_body={},
            records=[{"id": i} for i in range(7)],
            page_count=2,
            total_fetched=27,
        )
        assert strategy.next_params(resp) is None

    def test_engine_makes_two_requests_for_exactly_page_size_total(self, httpx_mock):
        """
        20 total records, page_size=20 → engine must make 2 requests:
          Request 1: returns 20 records (== page_size → continues)
          Request 2: returns 0 records (< page_size → stops)
        Total: 20 records, 2 HTTP requests.
        """
        # This test uses httpx_mock from pytest-httpx
        # First request: 20 records
        httpx_mock.add_response(
            status_code=200,
            json={"data": [{"id": i} for i in range(20)]},
        )
        # Second request: 0 records (end of data)
        httpx_mock.add_response(
            status_code=200,
            json={"data": []},
        )

        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
        from api_connector.services.pagination.engine import PaginationEngine

        # We need a minimal Endpoint mock for the engine
        mock_endpoint = MagicMock()
        mock_endpoint.connection_profile.base_url = "https://api.example.com"
        mock_endpoint.connection_profile.ssl_verify = True
        mock_endpoint.connection_profile.request_timeout = 30
        mock_endpoint.path = "/items"
        mock_endpoint.path_variables = {}
        mock_endpoint.query_params = []
        mock_endpoint.endpoint_headers = []
        mock_endpoint.data_root_path = "data"

        strategy = OffsetLimitStrategy(self.OL_PARAMS)
        safety = SafetyConfig(max_pages=10, max_records=10000)

        engine = PaginationEngine()
        all_records = []
        for records, _ in engine.paginate(
            endpoint=mock_endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=strategy,
            safety=safety,
        ):
            all_records.extend(records)

        # Exactly 20 records returned
        assert len(all_records) == 20, f"Expected 20, got {len(all_records)}"

        # Exactly 2 HTTP requests made
        requests_made = httpx_mock.get_requests()
        assert len(requests_made) == 2, (
            f"Expected 2 requests (page1→data, page2→empty), made {len(requests_made)}"
        )


# ── Edge Case 4: OAuth AC Refresh Token Revoked ───────────────────────────────


@pytest.mark.django_db
class TestOAuthACRefreshRevoked:
    """
    An expired OAuth AC profile whose refresh token is revoked or corrupt
    must return a structured 401 (not 500) from schema inference and preview.
    The connection test must return step 3 failure (overall 200, not 500).
    """

    def _create_expired_oauth_ac_profile(self):
        profile = ConnectionProfileFactory(auth_type=AuthType.OAUTH_AC)
        creds = {
            "client_id": "cid",
            "client_secret": "sec",
            "authorization_endpoint": "https://auth.example.com/auth",
            "token_endpoint": "https://auth.example.com/token",
        }
        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict(creds),
        )
        # Create OAuthToken with expired access token and invalid refresh token
        OAuthTokenFactory(
            connection_profile=profile,
            token_type=TokenType.OAUTH_AC,
            encrypted_token=encryption_service.encrypt("expired_access_token"),
            encrypted_refresh_token="NOT_VALID_FERNET_CIPHERTEXT",  # corrupt
            expires_at=timezone.now() - timedelta(hours=2),
        )
        return profile

    def test_schema_infer_returns_401_not_500_for_expired_oauth_ac(
        self, api_client, assert_no_credential_leak
    ):
        profile = self._create_expired_oauth_ac_profile()
        endpoint = EndpointFactory(connection_profile=profile, path="/items")

        response = api_client.post(
            f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/schema/infer/",
            data={},
            format="json",
        )

        assert response.status_code == 401, (
            f"Expected 401 (not 500) for expired OAuth AC on inference. "
            f"Got {response.status_code}: {response.data}"
        )
        assert response.data["error_code"] == "API_CONN_041"
        assert_no_credential_leak(response)

    def test_preview_returns_401_not_500_for_expired_oauth_ac(
        self, api_client, assert_no_credential_leak
    ):
        profile = self._create_expired_oauth_ac_profile()
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        SchemaFieldFactory(
            endpoint=endpoint, key_path="id", include=True, inferred_type="integer"
        )

        response = api_client.post(
            f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/preview/",
            data={"row_limit": 25},
            format="json",
        )

        assert response.status_code == 401, (
            f"Expected 401 (not 500) for expired OAuth AC on preview. "
            f"Got {response.status_code}: {response.data}"
        )
        assert response.data["error_code"] == "API_CONN_041"
        assert_no_credential_leak(response)

    def test_connection_test_returns_200_with_step3_failure(self, api_client):
        """
        Connection test on expired OAuth AC → overall 200 (test ran, it just failed at step 3).
        Step 3 must be failed with a reauth-related reason — not a generic error.
        """
        profile = self._create_expired_oauth_ac_profile()

        with (
            patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("1.2.3.4", 0))]),
            patch(
                "api_connector.services.connection_test.service.BaseHTTPClient.get",
                return_value=MagicMock(status_code=200),
            ),
        ):
            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/test/",
                data={},
                format="json",
            )

        assert response.status_code == 200, (
            f"Connection test action must return 200: {response.data}"
        )
        data = response.data

        assert "overall_passed" in data
        assert data["overall_passed"] is False

        steps = data["steps"]
        step3 = next((s for s in steps if s["name"] == "auth_injection"), None)
        assert step3 is not None
        assert step3["passed"] is False
        # Must NOT contain raw exception class names
        assert "OAuthACReauthorizationRequired" not in step3["message"]
        assert "InvalidToken" not in step3["message"]


# ── Edge Case 5: Cursor Absent from Response Body ─────────────────────────────


class TestCursorAbsent:
    """
    CursorStrategy.next_params() returns None when the cursor field is:
    - Absent from the response body (path not found)
    - Explicitly null
    But NOT when the cursor is integer 0 (valid cursor value).
    """

    CS_PARAMS = {
        "cursor_request_param": "after",
        "cursor_response_path": "meta.next_cursor",
    }

    def test_cursor_absent_from_body_stops_pagination(self):
        strategy = CursorStrategy(self.CS_PARAMS)

        # meta.next_cursor is absent (not null, just missing)
        resp = PaginatedResponse(
            raw_headers={},
            raw_body={"meta": {}},
            records=[{"id": 1}],
            page_count=1,
            total_fetched=1,
        )
        result = strategy.next_params(resp)
        assert result is None, "Absent cursor must stop pagination"

    def test_cursor_explicit_null_stops_pagination(self):
        strategy = CursorStrategy(self.CS_PARAMS)

        resp = PaginatedResponse(
            raw_headers={},
            raw_body={"meta": {"next_cursor": None}},
            records=[{"id": 1}],
            page_count=1,
            total_fetched=1,
        )
        result = strategy.next_params(resp)
        assert result is None, "Explicit null cursor must stop pagination"

    def test_cursor_empty_string_stops_pagination(self):
        strategy = CursorStrategy(self.CS_PARAMS)

        resp = PaginatedResponse(
            raw_headers={},
            raw_body={"meta": {"next_cursor": ""}},
            records=[{"id": 1}],
            page_count=1,
            total_fetched=1,
        )
        result = strategy.next_params(resp)
        assert result is None, "Empty string cursor must stop pagination"

    def test_cursor_integer_zero_continues_pagination(self):
        """
        CRITICAL: integer 0 IS a valid cursor value.
        'not cursor' / 'if not 0' would incorrectly stop here.
        """
        strategy = CursorStrategy(self.CS_PARAMS)

        resp = PaginatedResponse(
            raw_headers={},
            raw_body={"meta": {"next_cursor": 0}},
            records=[{"id": 1}],
            page_count=1,
            total_fetched=1,
        )
        result = strategy.next_params(resp)
        assert result is not None, (
            "CRITICAL: integer 0 is a valid cursor — pagination must NOT stop. "
            "Check CursorStrategy.next_params() for 'if not cursor' vs 'if cursor is None'."
        )
        assert result["after"] == 0

    def test_cursor_generator_stops_cleanly_without_exception(self, httpx_mock):
        """End-to-end: cursor strategy stops without raising any exception."""
        httpx_mock.add_response(
            status_code=200,
            json={"data": [{"id": 1}], "meta": {}},  # cursor absent → stops
        )

        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler
        from api_connector.services.pagination.engine import PaginationEngine

        mock_endpoint = MagicMock()
        mock_endpoint.connection_profile.base_url = "https://api.example.com"
        mock_endpoint.connection_profile.ssl_verify = True
        mock_endpoint.connection_profile.request_timeout = 30
        mock_endpoint.path = "/items"
        mock_endpoint.path_variables = {}
        mock_endpoint.query_params = []
        mock_endpoint.endpoint_headers = []
        mock_endpoint.data_root_path = "data"

        strategy = CursorStrategy(self.CS_PARAMS)
        safety = SafetyConfig(max_pages=10, max_records=1000)

        engine = PaginationEngine()
        all_records = []
        # Must not raise any exception
        for records, _ in engine.paginate(
            endpoint=mock_endpoint,
            auth_handler=NoneAuthHandler(),
            credentials={},
            strategy=strategy,
            safety=safety,
        ):
            all_records.extend(records)

        assert len(all_records) == 1
        assert len(httpx_mock.get_requests()) == 1  # Only one request made


# ── Edge Case 6: Invalid data_root_path → Empty Preview (not 500) ─────────────


@pytest.mark.django_db
class TestInvalidDataRootPath:
    """
    When data_root_path doesn't match the actual response structure,
    extract_records_at_path() returns [] (empty list).
    DataPreviewService returns 200 with empty rows — not 500.
    """

    def test_mismatched_data_root_path_returns_200_with_empty_rows(
        self, api_client, assert_no_credential_leak
    ):
        profile, endpoint = make_profile_endpoint()
        # Endpoint configured for "data.items" but API returns {"records": [...]}
        endpoint.data_root_path = "data.items"
        endpoint.save()
        SchemaFieldFactory(
            endpoint=endpoint, key_path="id", include=True, inferred_type="integer"
        )

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            from api_connector.services.data_preview import ColumnMeta, PreviewResult

            mock_svc = MagicMock()
            mock_svc.preview.return_value = PreviewResult(
                rows=[],
                columns=[
                    ColumnMeta(
                        name="id",
                        key_path="id",
                        effective_type="integer",
                        null_percentage=0.0,
                        sample_value=None,
                    )
                ],
                raw_response_body='{"records": [{"id": 1}]}',
                total_fetched=0,
                has_more=False,
            )
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/preview/",
                data={"row_limit": 25},
                format="json",
            )

        # Must be 200 — empty rows is a valid response (user's data_root_path misconfiguration)
        assert response.status_code == 200, (
            f"Expected 200 (empty rows is not a server error). Got: {response.status_code}"
        )
        assert response.data["rows"] == []
        assert response.data["total_fetched"] == 0
        assert response.data["has_more"] is False
        assert_no_credential_leak(response)

    def test_preview_result_has_columns_even_when_rows_empty(
        self, api_client, assert_no_credential_leak
    ):
        """Even with 0 rows, columns metadata is returned (allows UI to show headers)."""
        profile, endpoint = make_profile_endpoint()
        SchemaFieldFactory(
            endpoint=endpoint, key_path="name", include=True, inferred_type="string"
        )

        with patch("api_connector.views.endpoint.DataPreviewService") as mock_svc_cls:
            from api_connector.services.data_preview import ColumnMeta, PreviewResult

            mock_svc = MagicMock()
            mock_svc.preview.return_value = PreviewResult(
                rows=[],
                columns=[ColumnMeta("name", "name", "string", 0.0, None)],
                raw_response_body="{}",
                total_fetched=0,
                has_more=False,
            )
            mock_svc_cls.return_value = mock_svc

            response = api_client.post(
                f"/api/connector/profiles/{profile.pk}/endpoints/{endpoint.pk}/preview/",
                data={"row_limit": 10},
                format="json",
            )

        assert response.status_code == 200
        assert len(response.data["columns"]) == 1
        assert_no_credential_leak(response)


# ── OAuthACState Cleanup Test ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestOAuthACStateCleanup:
    """
    cleanup_oauth_ac_states management command:
    - Deletes used + old records
    - Deletes expired records
    - Preserves active (unused + unexpired) records
    """

    def test_cleanup_command_runs_without_error_on_empty_table(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("cleanup_oauth_ac_states", stdout=out)
        output = out.getvalue()
        assert "Deleted" in output

    def test_cleanup_deletes_used_records(self):
        from api_connector.models import OAuthACState
        from tests.factories import OAuthACStateFactory

        profile = ConnectionProfileFactory()
        # Used record (old) — should be deleted
        OAuthACStateFactory(
            connection_profile=profile,
            used=True,
            expires_at=timezone.now() - timedelta(hours=25),
        )
        # Expired unused record — should be deleted
        OAuthACStateFactory(
            connection_profile=profile,
            used=False,
            expires_at=timezone.now() - timedelta(hours=25),
        )
        # Active record (unused + not expired) — must be preserved
        OAuthACStateFactory(
            connection_profile=profile,
            used=False,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        initial_count = OAuthACState.objects.count()
        assert initial_count == 3

        from django.core.management import call_command

        call_command("cleanup_oauth_ac_states")

        remaining = OAuthACState.objects.count()
        assert remaining == 1, f"Expected 1 active record to remain, got {remaining}"
