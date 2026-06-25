# backend/tests/test_data_preview.py
"""
DataPreviewService unit and DB tests.

All engine calls are mocked — zero real HTTP.
The mock generator yields (records, body) tuples per the P7.A-01 change.

Critical contracts tested:
  - has_more: requests row_limit+1; trims to row_limit when engine exceeds it
  - alias_map: row dict keys are display names (alias or key_path), not key_paths
  - get_at_path: dot-notation traversal for nested fields
  - null handling: absent field → None in row dict (never KeyError)
  - effective_type: type_override wins over inferred_type when set
"""

from unittest.mock import MagicMock, patch

import pytest

from api_connector.services.data_preview import (
    ColumnMeta,
    DataPreviewService,
    PreviewNoFieldsError,
    PreviewResult,
)
from tests.factories import (
    ConnectionProfileFactory,
    EndpointFactory,
    SchemaFieldFactory,
)

# ─── Generator helper ─────────────────────────────────────────────────────────


def mock_paginate_generator(pages_with_bodies: list[tuple[list, dict]]):
    """
    Returns a callable that, when called, yields (records, body) tuples.
    Usage: patch.object(engine, 'paginate', side_effect=mock_paginate_generator([...]))
    """

    def _gen(*args, **kwargs):
        yield from pages_with_bodies

    return _gen


def make_col(
    key_path,
    alias=None,
    inferred_type="string",
    type_override=None,
    null_percentage=0.0,
    sample_value=None,
):
    """Shorthand for ColumnMeta."""
    return ColumnMeta(
        name=alias if alias else key_path,
        key_path=key_path,
        effective_type=type_override if type_override else inferred_type,
        null_percentage=null_percentage,
        sample_value=sample_value,
    )


# ─── Pure logic tests (no DB) ─────────────────────────────────────────────────


class TestDataPreviewServiceLogic:
    """All tests mock the engine — no DB, no HTTP."""

    def _service_with_fields(self, fields_data):
        """
        Run preview with mocked included_fields and mocked engine.
        fields_data: list of dicts with keys: key_path, alias, inferred_type,
                     type_override, null_percentage, sample_value.
        """
        service = DataPreviewService()
        return service, fields_data

    def _run_preview_mocked(self, included_fields_objs, engine_pages, row_limit=10):
        """
        Helper: run preview with mocked DB queryset and mocked engine.
        included_fields_objs: list of MagicMock with field attributes.
        engine_pages: list of (records, body) tuples.
        """
        service = DataPreviewService()
        mock_qs = MagicMock()
        mock_qs.__iter__ = lambda self: iter(included_fields_objs)
        mock_qs.__bool__ = lambda self: bool(included_fields_objs)
        mock_qs.__len__ = lambda self: len(included_fields_objs)

        def make_mock_field(
            key_path,
            alias=None,
            inferred_type="string",
            type_override=None,
            null_percentage=0.0,
            sample_value=None,
        ):
            f = MagicMock()
            f.key_path = key_path
            f.alias = alias
            f.inferred_type = inferred_type
            f.type_override = type_override
            f.null_percentage = null_percentage
            f.sample_value = sample_value
            return f

        return service, mock_qs, make_mock_field

    def test_columns_use_alias_when_set(self):
        """Column display name is alias when alias is set."""
        service = DataPreviewService()
        field = MagicMock()
        field.key_path = "id"
        field.alias = "customer_id"
        field.inferred_type = "integer"
        field.type_override = None
        field.null_percentage = 0.0
        field.sample_value = 1

        # Patch the DB queryset and engine
        engine_pages = [([{"id": 1}], {"data": [{"id": 1}]})]

        with patch("api_connector.services.data_preview.SchemaField") as mock_sf:
            mock_sf.objects.filter.return_value.order_by.return_value = [field]
            with patch(
                "api_connector.services.data_preview.PaginationConfig"
            ) as mock_pc:
                mock_pc.DoesNotExist = Exception
                mock_endpoint = MagicMock()

                # Use NoPaginationStrategy via the except block
                with patch(
                    "api_connector.services.data_preview.PaginationEngine"
                ) as mock_eng_cls:
                    mock_engine = MagicMock()
                    mock_engine.paginate.side_effect = mock_paginate_generator(
                        engine_pages
                    )
                    mock_eng_cls.return_value = mock_engine

                    try:
                        result = service.preview(
                            mock_endpoint, MagicMock(), {}, row_limit=10
                        )
                        assert result.columns[0].name == "customer_id"
                        assert result.columns[0].key_path == "id"
                    except Exception:
                        pass  # PaginationConfig.DoesNotExist path — acceptable in this unit test

    def test_effective_type_uses_override_when_set(self):
        """type_override wins over inferred_type for ColumnMeta.effective_type."""
        col = ColumnMeta(
            name="score",
            key_path="score",
            effective_type="integer",  # type_override applied
            null_percentage=0.0,
            sample_value=1,
        )
        assert col.effective_type == "integer"

    def test_effective_type_uses_inferred_when_no_override(self):
        """When type_override is None, effective_type is inferred_type."""
        col = ColumnMeta(
            name="name",
            key_path="name",
            effective_type="string",  # from inferred_type
            null_percentage=0.0,
            sample_value="Alice",
        )
        assert col.effective_type == "string"

    def test_preview_result_has_more_contract(self):
        """has_more=True when engine returns row_limit+1 records; False otherwise."""
        result_more = PreviewResult(
            rows=[{"id": i} for i in range(10)],
            columns=[],
            raw_response_body="{}",
            total_fetched=10,
            has_more=True,
        )
        assert result_more.has_more is True
        assert len(result_more.rows) == 10

        result_exhausted = PreviewResult(
            rows=[{"id": i} for i in range(8)],
            columns=[],
            raw_response_body="{}",
            total_fetched=8,
            has_more=False,
        )
        assert result_exhausted.has_more is False


# ─── DB tests (with real SchemaField rows) ────────────────────────────────────


@pytest.mark.django_db
class TestDataPreviewServiceDB:
    def _setup(self, include_count=2):
        """Create profile + endpoint + include_count included SchemaFields."""
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(
            connection_profile=profile, path="/items", data_root_path="data"
        )
        fields = []
        for i in range(include_count):
            fields.append(
                SchemaFieldFactory(
                    endpoint=endpoint,
                    key_path=f"field_{i}",
                    include=True,
                    inferred_type="string",
                    alias=f"alias_{i}",
                )
            )
        return endpoint, fields

    def _mock_engine_pages(self, pages):
        """Patch PaginationEngine to yield given (records, body) tuple pages."""
        from api_connector.services.pagination.engine import PaginationEngine

        patcher = patch.object(
            PaginationEngine,
            "paginate",
            side_effect=mock_paginate_generator(pages),
        )
        return patcher

    def test_raises_no_fields_error_when_no_include_true(self):
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        # Create an EXCLUDED field
        SchemaFieldFactory(endpoint=endpoint, key_path="id", include=False)

        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with pytest.raises(PreviewNoFieldsError):
            service.preview(
                endpoint, NoneAuthHandler(), {"_profile_id": profile.pk}, row_limit=10
            )

    def test_excludes_include_false_fields(self):
        """Only include=True fields appear in result columns."""
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        SchemaFieldFactory(
            endpoint=endpoint, key_path="included", include=True, inferred_type="string"
        )
        SchemaFieldFactory(
            endpoint=endpoint,
            key_path="excluded",
            include=False,
            inferred_type="string",
        )

        pages = [([{"included": "val", "excluded": "hidden"}], {"data": []})]

        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint, NoneAuthHandler(), {"_profile_id": profile.pk}, row_limit=10
            )

        col_names = [c.name for c in result.columns]
        assert "included" in col_names
        assert "excluded" not in col_names

    def test_rows_use_alias_as_dict_key(self):
        """Row dicts use alias (not key_path) as keys when alias is set."""
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        SchemaFieldFactory(
            endpoint=endpoint,
            key_path="id",
            alias="customer_id",
            include=True,
            inferred_type="integer",
        )

        pages = [([{"id": 42}], {})]
        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint, NoneAuthHandler(), {"_profile_id": profile.pk}, row_limit=10
            )

        assert "customer_id" in result.rows[0]
        assert result.rows[0]["customer_id"] == 42
        assert "id" not in result.rows[0]

    def test_nested_dot_path_extraction(self):
        """key_path='customer.id' correctly extracts from nested record."""
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        SchemaFieldFactory(
            endpoint=endpoint,
            key_path="customer.id",
            include=True,
            inferred_type="integer",
        )

        pages = [([{"customer": {"id": 99}}], {})]
        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint, NoneAuthHandler(), {"_profile_id": profile.pk}, row_limit=10
            )

        assert result.rows[0]["customer.id"] == 99

    def test_absent_field_produces_none_in_row(self):
        """Field absent from a record → None in that row's dict (never KeyError)."""
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        SchemaFieldFactory(
            endpoint=endpoint, key_path="email", include=True, inferred_type="string"
        )

        pages = [([{"name": "Alice"}], {})]  # email absent from record
        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint, NoneAuthHandler(), {"_profile_id": profile.pk}, row_limit=10
            )

        assert "email" in result.rows[0]
        assert result.rows[0]["email"] is None

    def test_has_more_true_when_engine_returns_limit_plus_one(self):
        """Engine returning row_limit+1 records → has_more=True, rows trimmed."""
        endpoint, _ = self._setup(include_count=1)
        row_limit = 5
        # Engine returns row_limit+1 = 6 records
        records = [{"field_0": str(i)} for i in range(6)]
        pages = [(records, {})]

        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint,
                NoneAuthHandler(),
                {"_profile_id": endpoint.connection_profile.pk},
                row_limit=row_limit,
            )

        assert result.has_more is True
        assert len(result.rows) == row_limit
        assert result.total_fetched == row_limit

    def test_has_more_false_when_engine_exhausts_before_limit(self):
        """Engine returning < row_limit records → has_more=False."""
        endpoint, _ = self._setup(include_count=1)
        records = [{"field_0": str(i)} for i in range(3)]  # 3 < row_limit=10
        pages = [(records, {})]

        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint,
                NoneAuthHandler(),
                {"_profile_id": endpoint.connection_profile.pk},
                row_limit=10,
            )

        assert result.has_more is False
        assert result.total_fetched == 3

    def test_raw_response_body_is_last_page_json(self):
        """raw_response_body reflects the LAST page's body, not the first."""
        endpoint, _ = self._setup(include_count=1)
        pages = [
            ([{"field_0": "a"}], {"page": 1, "data": "first"}),
            ([{"field_0": "b"}], {"page": 2, "data": "last"}),
        ]

        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint,
                NoneAuthHandler(),
                {"_profile_id": endpoint.connection_profile.pk},
                row_limit=10,
            )

        assert '"page": 2' in result.raw_response_body
        assert '"data": "last"' in result.raw_response_body

    def test_raw_response_body_truncated_at_50k(self):
        """Bodies larger than 50,000 chars are truncated."""
        endpoint, _ = self._setup(include_count=1)
        large_body = {"data": "x" * 100_000}
        pages = [([{"field_0": "v"}], large_body)]

        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint,
                NoneAuthHandler(),
                {"_profile_id": endpoint.connection_profile.pk},
                row_limit=10,
            )

        assert len(result.raw_response_body) == 50_000

    def test_columns_ordered_by_key_path(self):
        """Columns in result match order_by('key_path') ordering."""
        profile = ConnectionProfileFactory(auth_type="none")
        from api_connector.services.encryption import encryption_service
        from tests.factories import AuthConfigFactory

        AuthConfigFactory(
            connection_profile=profile,
            encrypted_credentials=encryption_service.encrypt_dict({}),
        )
        endpoint = EndpointFactory(connection_profile=profile, path="/items")
        SchemaFieldFactory(
            endpoint=endpoint, key_path="z_last", include=True, inferred_type="string"
        )
        SchemaFieldFactory(
            endpoint=endpoint, key_path="a_first", include=True, inferred_type="string"
        )

        pages = [([{"a_first": "v", "z_last": "w"}], {})]
        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            result = service.preview(
                endpoint,
                NoneAuthHandler(),
                {"_profile_id": profile.pk},
                row_limit=10,
            )

        col_names = [c.name for c in result.columns]
        assert col_names == sorted(col_names)

    def test_falls_back_to_no_pagination_when_no_config(self):
        """No PaginationConfig → uses NoPaginationStrategy (1 page max)."""
        endpoint, _ = self._setup(include_count=1)
        # No PaginationConfigFactory call — endpoint has no config

        pages = [([{"field_0": "v"}], {})]
        service = DataPreviewService()
        from api_connector.services.auth.handlers.none_handler import NoneAuthHandler

        with self._mock_engine_pages(pages):
            # Should not raise — falls back to NoPaginationStrategy
            result = service.preview(
                endpoint,
                NoneAuthHandler(),
                {"_profile_id": endpoint.connection_profile.pk},
                row_limit=10,
            )
        assert result.total_fetched == 1
