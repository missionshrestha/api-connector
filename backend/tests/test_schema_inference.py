# backend/tests/test_schema_inference.py
"""
Schema inference engine unit and DB tests.

Pure logic tests (walker, type inference) use no DB.
_fetch_sample() is mocked in orchestration tests — no real HTTP calls.
"""
from unittest.mock import patch

import pytest

from api_connector.services.schema_inference.engine import (
    SchemaInferenceEngine,
    _infer_type_from_values,
)
from api_connector.services.schema_inference.types import (
    ARRAY_OF_OBJECTS_SENTINEL,
    ARRAY_OF_PRIMITIVES_SENTINEL,
    SchemaFieldSpec,
    SchemaInferenceError,
    SchemaInferenceNoRecordsError,
)
from tests.factories import (
    ConnectionProfileFactory,
    EndpointFactory,
    SchemaFieldFactory,
)


# ─── Walker tests (no DB) ──────────────────────────────────────────────────────

class TestWalkRecord:
    engine = SchemaInferenceEngine()

    def test_flat_record(self):
        result = self.engine._walk_record({"id": 1, "name": "Alice"}, "", 0)
        assert result == {"id": 1, "name": "Alice"}

    def test_nested_dict_recurses_no_emit(self):
        result = self.engine._walk_record({"user": {"id": 1}}, "", 0)
        assert "user" not in result  # dict itself NOT emitted
        assert result["user.id"] == 1

    def test_array_of_objects_emits_sentinel_and_recurses(self):
        result = self.engine._walk_record({"items": [{"id": 1, "name": "x"}]}, "", 0)
        assert result["items"] == ARRAY_OF_OBJECTS_SENTINEL
        assert result["items.id"] == 1
        assert result["items.name"] == "x"

    def test_array_of_primitives_emits_sentinel(self):
        result = self.engine._walk_record({"tags": ["a", "b"]}, "", 0)
        assert result["tags"] == ARRAY_OF_PRIMITIVES_SENTINEL

    def test_empty_list_emits_primitives_sentinel(self):
        result = self.engine._walk_record({"items": []}, "", 0)
        assert result["items"] == ARRAY_OF_PRIMITIVES_SENTINEL

    def test_explicit_none_emitted_as_none(self):
        result = self.engine._walk_record({"email": None}, "", 0)
        assert result == {"email": None}

    def test_deeply_nested_path(self):
        result = self.engine._walk_record(
            {"a": {"b": {"c": {"d": 42}}}}, "", 0
        )
        assert result["a.b.c.d"] == 42

    def test_depth_cap_stops_recursion(self):
        engine = SchemaInferenceEngine()
        engine.max_depth = 2
        # At depth 0: "a" (dict) → recurse
        # At depth 1: "b" (dict) → recurse
        # At depth 2: cap hit — return {}
        result = engine._walk_record({"a": {"b": {"c": 1}}}, "", 0)
        assert "a.b.c" not in result  # depth cap applied

    def test_non_dict_input_returns_empty(self):
        result = self.engine._walk_record("not a dict", "", 0)  # type: ignore[arg-type]
        assert result == {}

    def test_empty_dict_returns_empty(self):
        assert self.engine._walk_record({}, "", 0) == {}

    def test_mixed_array_not_all_dicts_emits_primitives_sentinel(self):
        """[dict, str] is not all-dicts → primitives sentinel"""
        result = self.engine._walk_record({"data": [{"id": 1}, "oops"]}, "", 0)
        assert result["data"] == ARRAY_OF_PRIMITIVES_SENTINEL


# ─── Type inference tests (no DB) ─────────────────────────────────────────────

class TestInferTypeFromValues:
    def test_empty_returns_null(self):
        assert _infer_type_from_values([]) == "null"

    def test_all_aoo_sentinels(self):
        assert _infer_type_from_values([ARRAY_OF_OBJECTS_SENTINEL, ARRAY_OF_OBJECTS_SENTINEL]) == "array_of_objects"

    def test_all_aop_sentinels(self):
        assert _infer_type_from_values([ARRAY_OF_PRIMITIVES_SENTINEL]) == "array_of_primitives"

    def test_boolean_pure_true_false(self):
        assert _infer_type_from_values([True, False, True]) == "boolean"

    def test_boolean_before_integer_critical(self):
        """isinstance(True, int) is True — bool MUST be checked before int."""
        assert _infer_type_from_values([True]) == "boolean"
        assert _infer_type_from_values([False]) == "boolean"

    def test_bool_and_int_mixed_returns_mixed(self):
        """True + 1 is neither pure bool nor pure int."""
        assert _infer_type_from_values([True, 1]) == "mixed"

    def test_pure_integers(self):
        assert _infer_type_from_values([1, 2, 3]) == "integer"

    def test_int_and_float_widens_to_float(self):
        assert _infer_type_from_values([1, 2, 3.5]) == "float"

    def test_pure_floats(self):
        assert _infer_type_from_values([1.1, 2.2]) == "float"

    def test_float_zero_stays_float(self):
        assert _infer_type_from_values([0.0, 1.0]) == "float"

    def test_datetime_detected(self):
        assert _infer_type_from_values(["2024-01-15T10:30:00Z", "2024-06-01T00:00:00"]) == "datetime"

    def test_date_detected(self):
        assert _infer_type_from_values(["2024-01-15", "2023-12-31"]) == "date"

    def test_datetime_checked_before_date(self):
        """Datetime strings also match date pattern — datetime must win."""
        assert _infer_type_from_values(["2024-01-15T10:30:00Z"]) == "datetime"

    def test_pure_strings(self):
        assert _infer_type_from_values(["abc", "def"]) == "string"

    def test_string_and_int_returns_mixed(self):
        assert _infer_type_from_values(["abc", 1]) == "mixed"

    def test_none_not_in_values_handled_by_caller(self):
        """Callers filter None before calling. This test documents the contract."""
        # If None is passed (caller bug), it lands in "mixed"
        result = _infer_type_from_values([1, None])
        assert result == "mixed"  # not "integer" — None breaks the all-numeric check


# ─── infer() orchestration tests (mocked _fetch_sample) ──────────────────────

class TestSchemaInferenceEngineInfer:
    def test_correct_null_percentage_for_absent_path(self):
        """Field present in 3 of 5 records → null_percentage = 0.4 (2 absent)."""
        records = [
            {"id": 1, "name": "A"},
            {"id": 2},               # name absent
            {"id": 3, "name": "C"},
            {"id": 4, "name": "D"},
            {"id": 5},               # name absent
        ]
        engine = SchemaInferenceEngine()
        with patch.object(engine, "_fetch_sample", return_value=records):
            specs = engine.infer(None, None, {})

        name_spec = next(s for s in specs if s.key_path == "name")
        assert abs(name_spec.null_percentage - 0.4) < 0.001
        assert name_spec.inferred_type == "string"

    def test_correct_null_percentage_for_explicit_none(self):
        """Field with None value in 1 of 3 records → null_percentage = 1/3."""
        records = [
            {"score": 10},
            {"score": None},
            {"score": 20},
        ]
        engine = SchemaInferenceEngine()
        with patch.object(engine, "_fetch_sample", return_value=records):
            specs = engine.infer(None, None, {})

        score_spec = next(s for s in specs if s.key_path == "score")
        assert abs(score_spec.null_percentage - 1 / 3) < 0.001
        assert score_spec.inferred_type == "integer"

    def test_empty_records_raises_no_records_error(self):
        engine = SchemaInferenceEngine()
        with patch.object(engine, "_fetch_sample", return_value=[]):
            with pytest.raises(SchemaInferenceNoRecordsError):
                engine.infer(None, None, {})

    def test_sample_value_skips_sentinels(self):
        records = [{"items": [{"id": 1}]}]
        engine = SchemaInferenceEngine()
        with patch.object(engine, "_fetch_sample", return_value=records):
            specs = engine.infer(None, None, {})

        items_spec = next(s for s in specs if s.key_path == "items")
        assert items_spec.sample_value is None  # sentinel not stored as sample

        child_spec = next(s for s in specs if s.key_path == "items.id")
        assert child_spec.sample_value == 1

    def test_specs_sorted_by_key_path(self):
        records = [{"z": 1, "a": 2, "m": 3}]
        engine = SchemaInferenceEngine()
        with patch.object(engine, "_fetch_sample", return_value=records):
            specs = engine.infer(None, None, {})

        paths = [s.key_path for s in specs]
        assert paths == sorted(paths)

    def test_fetch_error_raises_schema_inference_error(self):
        from api_connector.services.pagination.engine import PaginationEngineError
        engine = SchemaInferenceEngine()
        with patch.object(
            engine, "_fetch_sample",
            side_effect=PaginationEngineError("parse error")
        ):
            with pytest.raises(SchemaInferenceError):
                engine.infer(None, None, {})


# ─── upsert_fields() DB tests ─────────────────────────────────────────────────

@pytest.mark.django_db
class TestUpsertFields:
    def _specs(self, **overrides):
        defaults = dict(
            key_path="customer.id", inferred_type="integer",
            null_percentage=0.0, sample_value=1
        )
        defaults.update(overrides)
        return [SchemaFieldSpec(**defaults)]

    def test_first_run_creates_fields(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        engine = SchemaInferenceEngine()
        specs = [
            SchemaFieldSpec("user.id", "integer", 0.0, 1),
            SchemaFieldSpec("user.name", "string", 0.1, "Alice"),
        ]
        result = engine.upsert_fields(endpoint, specs)
        assert len(result) == 2
        paths = {sf.key_path for sf in result}
        assert paths == {"user.id", "user.name"}

    def test_rerun_preserves_alias(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        # Set alias on existing field
        sf = SchemaFieldFactory(
            endpoint=endpoint, key_path="id", alias="customer_id",
            inferred_type="string",
        )
        engine = SchemaInferenceEngine()
        specs = [SchemaFieldSpec("id", "integer", 0.0, 1)]
        result = engine.upsert_fields(endpoint, specs)
        sf.refresh_from_db()
        assert sf.alias == "customer_id"  # PRESERVED
        assert sf.inferred_type == "integer"  # REFRESHED

    def test_rerun_preserves_include_false(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        SchemaFieldFactory(endpoint=endpoint, key_path="internal", include=False)
        engine = SchemaInferenceEngine()
        specs = [SchemaFieldSpec("internal", "string", 0.0, "x")]
        engine.upsert_fields(endpoint, specs)
        from api_connector.models import SchemaField
        sf = SchemaField.objects.get(endpoint=endpoint, key_path="internal")
        assert sf.include is False  # PRESERVED

    def test_disappeared_path_marked_stale(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        old_sf = SchemaFieldFactory(endpoint=endpoint, key_path="legacy_field")
        engine = SchemaInferenceEngine()
        # Re-run without legacy_field
        specs = [SchemaFieldSpec("new_field", "string", 0.0, "x")]
        engine.upsert_fields(endpoint, specs)
        old_sf.refresh_from_db()
        assert old_sf.stale is True

    def test_new_path_created_with_include_true(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        engine = SchemaInferenceEngine()
        specs = [SchemaFieldSpec("brand_new", "boolean", 0.0, True)]
        result = engine.upsert_fields(endpoint, specs)
        sf = next(s for s in result if s.key_path == "brand_new")
        assert sf.include is True
        assert sf.stale is False

    def test_rerun_updates_inferred_type(self):
        profile = ConnectionProfileFactory()
        endpoint = EndpointFactory(connection_profile=profile)
        SchemaFieldFactory(endpoint=endpoint, key_path="score", inferred_type="string")
        engine = SchemaInferenceEngine()
        specs = [SchemaFieldSpec("score", "float", 0.0, 9.5)]
        engine.upsert_fields(endpoint, specs)
        from api_connector.models import SchemaField
        sf = SchemaField.objects.get(endpoint=endpoint, key_path="score")
        assert sf.inferred_type == "float"  # UPDATED