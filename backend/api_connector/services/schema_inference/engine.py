# backend/api_connector/services/schema_inference/engine.py
"""
SchemaInferenceEngine — recursive walker, type inference, and DB upsert.

ADR (inline): Two-pass inference strategy.
  Pass 1: Walk all records → accumulate per-path value lists + per-record path sets.
  Pass 2: For each path, calculate null_percentage and infer type.
  Rationale: null_percentage requires total_records (known only after full walk).
  A one-pass running-average approach would produce incorrect results for paths
  that appear in some records but not others.

Security:
  - NEVER log credentials, sample_value contents, or raw response bodies.
  - Log only structural metadata: endpoint_id, record count, path count, duration.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from typing import Any

from django.conf import settings
from django.db import transaction

from api_connector.models import SchemaField
from api_connector.services.schema_inference.types import (
    ARRAY_OF_OBJECTS_SENTINEL,
    ARRAY_OF_PRIMITIVES_SENTINEL,
    SchemaFieldSpec,
    SchemaInferenceError,
    SchemaInferenceNoRecordsError,
)

logger = logging.getLogger("api_connector.schema_inference")

# ── Compiled regex patterns (module-level for performance) ─────────────────────
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Type inference ─────────────────────────────────────────────────────────────

def _infer_type_from_values(values: list) -> str:
    """
    Infer a field's type from a list of NON-null values collected across all records.
    Callers must filter None before calling — None represents absence/null and is
    captured in null_percentage, not type inference.

    Rule order is critical:
      1. Empty list → "null" (all values were absent or None)
      2. Sentinels → array types
      3. bool BEFORE int (isinstance(True, int) is True in Python)
      4. Numeric widening: int+float → float
      5. String pattern matching: datetime before date
      6. Default → "mixed"
    """
    if not values:
        return "null"

    # Sentinel checks
    if all(v == ARRAY_OF_OBJECTS_SENTINEL for v in values):
        return "array_of_objects"
    if all(v == ARRAY_OF_PRIMITIVES_SENTINEL for v in values):
        return "array_of_primitives"

    # ⚠️ BOOL BEFORE INT — isinstance(True, int) is True in Python
    if all(isinstance(v, bool) for v in values):
        return "boolean"

    # Numeric widening
    all_numeric = all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in values
    )
    if all_numeric:
        if any(isinstance(v, float) for v in values):
            return "float"
        return "integer"

    # String type analysis
    if all(isinstance(v, str) for v in values):
        if all(_DATETIME_RE.match(v) for v in values):
            return "datetime"
        if all(_DATE_RE.match(v) for v in values):
            return "date"
        return "string"

    return "mixed"


# ── Engine ─────────────────────────────────────────────────────────────────────

class SchemaInferenceEngine:
    """
    Stateless inference engine.
    infer() is the only public method callers need.
    upsert_fields() is the only DB write method.
    """

    def __init__(self) -> None:
        self.max_depth: int = getattr(settings, "SCHEMA_INFERENCE_MAX_DEPTH", 10)

    def _walk_record(self, obj: dict, prefix: str, depth: int) -> dict[str, Any]:
        """
        Recursively flatten one JSON record into a {dot.path: value} dict.

        Rules:
          - dict values: recurse but do NOT emit the dict itself as a value
            (emitting dicts would classify them as "mixed", not traversable)
          - list of all-dicts: emit ARRAY_OF_OBJECTS_SENTINEL for the path
            AND recurse into the FIRST item to discover child paths
          - list (empty or non-dicts): emit ARRAY_OF_PRIMITIVES_SENTINEL
          - scalar / None: emit as-is (None represents explicit null from API)
          - depth >= max_depth: stop recursing (no partial dict iteration beyond cap)
        """
        result: dict[str, Any] = {}

        if not isinstance(obj, dict) or depth >= self.max_depth:
            return result

        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                # Recurse; do not emit the dict itself
                result.update(self._walk_record(value, path, depth + 1))

            elif isinstance(value, list):
                if value and all(isinstance(item, dict) for item in value):
                    result[path] = ARRAY_OF_OBJECTS_SENTINEL
                    # Discover child paths from the first element
                    result.update(self._walk_record(value[0], path, depth + 1))
                else:
                    # Empty list or list of primitives
                    result[path] = ARRAY_OF_PRIMITIVES_SENTINEL

            else:
                # Scalar or explicit None
                result[path] = value

        return result

    def _fetch_sample(
        self,
        endpoint: Any,
        auth_handler: Any,
        credentials: dict,
    ) -> list[dict]:
        """
        Fetch up to 300 records using the configured pagination strategy.
        Returns a flat list of record dicts (may be shorter than 300).

        Raises PaginationEngineError, HTTPStatusError, HTTPTimeoutError,
        HTTPNetworkError on network/API failures — infer() converts these.
        """
        from api_connector.models import PaginationConfig
        from api_connector.services.pagination.engine import PaginationEngine
        from api_connector.services.pagination.registry import pagination_registry
        from api_connector.services.pagination.strategies import NoPaginationStrategy
        from api_connector.services.pagination.types import SafetyConfig

        ROW_LIMIT = 300
        MAX_PAGES = 3

        try:
            config = endpoint.pagination_config
            strategy = pagination_registry.get(
                config.strategy, params=config.strategy_params or {}
            )
            safety = SafetyConfig(
                max_pages=MAX_PAGES,
                max_records=ROW_LIMIT,
                inter_page_delay_ms=config.inter_page_delay_ms,
                max_retries=config.max_retries,
            )
        except PaginationConfig.DoesNotExist:
            strategy = NoPaginationStrategy()
            safety = SafetyConfig(max_pages=1, max_records=ROW_LIMIT)

        engine = PaginationEngine()
        records: list[dict] = []

        for page_records in engine.paginate(
            endpoint=endpoint,
            auth_handler=auth_handler,
            credentials=credentials,
            strategy=strategy,
            safety=safety,
            row_limit=ROW_LIMIT,
        ):
            records.extend(page_records)
            if len(records) >= ROW_LIMIT:
                break

        return records[:ROW_LIMIT]

    def infer(
        self,
        endpoint: Any,
        auth_handler: Any,
        credentials: dict,
    ) -> list[SchemaFieldSpec]:
        """
        Run schema inference for an endpoint.

        Returns a sorted list of SchemaFieldSpec — one per discovered key_path.
        Raises SchemaInferenceNoRecordsError if no records were found.
        Raises SchemaInferenceError on network or parsing failure.
        """
        from api_connector.services.pagination.engine import PaginationEngineError
        from api_connector.services.http_exceptions import (
            HTTPNetworkError, HTTPStatusError, HTTPTimeoutError,
        )

        start = time.monotonic()

        try:
            records = self._fetch_sample(endpoint, auth_handler, credentials)
        except (
            PaginationEngineError, HTTPStatusError, HTTPTimeoutError, HTTPNetworkError
        ) as exc:
            raise SchemaInferenceError(str(exc)) from exc

        if not records:
            raise SchemaInferenceNoRecordsError(
                "No records found in the API response. "
                "Verify the data_root_path is correct and that the endpoint returns data."
            )

        total = len(records)

        if total < 10:
            logger.warning(
                "Schema inference: endpoint=%s low sample count (%d records) — "
                "type inference may be unreliable",
                getattr(endpoint, "pk", None),
                total,
            )

        # Pass 1: Walk all records
        path_values: dict[str, list] = defaultdict(list)
        path_presence: list[set] = []

        for record in records:
            flat = self._walk_record(record, "", 0)
            path_presence.append(set(flat.keys()))
            for path, value in flat.items():
                path_values[path].append(value)

        # Pass 2: Aggregate per path
        all_paths: set[str] = set()
        for paths in path_presence:
            all_paths.update(paths)

        specs: list[SchemaFieldSpec] = []

        for path in sorted(all_paths):
            values = path_values[path]

            # null_count = records where path was absent + records where value is None
            absent_count = sum(1 for rp in path_presence if path not in rp)
            none_count = sum(1 for v in values if v is None)
            null_count = absent_count + none_count
            null_percentage = null_count / total if total > 0 else 0.0

            non_null_values = [v for v in values if v is not None]
            inferred_type = _infer_type_from_values(non_null_values)

            # Sample value: first non-null, non-sentinel value
            sample_value = next(
                (
                    v for v in non_null_values
                    if v not in (ARRAY_OF_OBJECTS_SENTINEL, ARRAY_OF_PRIMITIVES_SENTINEL)
                ),
                None,
            )

            specs.append(
                SchemaFieldSpec(
                    key_path=path,
                    inferred_type=inferred_type,
                    null_percentage=null_percentage,
                    sample_value=sample_value,
                )
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "Schema inference: endpoint=%s records_sampled=%d paths_discovered=%d duration_ms=%d",
            getattr(endpoint, "pk", None),
            total,
            len(specs),
            duration_ms,
        )

        return specs

    def upsert_fields(
        self,
        endpoint: Any,
        specs: list[SchemaFieldSpec],
    ) -> "list[SchemaField]":
        """
        Write inference results to the DB, preserving user edits on re-run.

        Preservation contract (NEVER overwrite on re-run):
          alias, include, type_override, array_handling

        Always refresh on re-run:
          inferred_type, null_percentage, sample_value, stale

        New paths → created with include=True, stale=False.
        Existing paths → updated with refreshed inference values, stale=False.
        Paths that disappeared → stale=True (not deleted).
        """
        existing: dict[str, SchemaField] = {
            sf.key_path: sf
            for sf in SchemaField.objects.filter(endpoint=endpoint)
        }
        new_paths = {spec.key_path for spec in specs}

        to_create: list[SchemaField] = []
        to_update: list[SchemaField] = []

        for spec in specs:
            if spec.key_path in existing:
                sf = existing[spec.key_path]
                # Refresh inference values; preserve user edits
                sf.inferred_type = spec.inferred_type
                sf.null_percentage = spec.null_percentage
                sf.sample_value = spec.sample_value
                sf.stale = False
                to_update.append(sf)
            else:
                to_create.append(
                    SchemaField(
                        endpoint=endpoint,
                        key_path=spec.key_path,
                        inferred_type=spec.inferred_type,
                        null_percentage=spec.null_percentage,
                        sample_value=spec.sample_value,
                        stale=False,
                        include=True,
                    )
                )

        # Mark disappeared paths as stale
        for key_path, sf in existing.items():
            if key_path not in new_paths:
                sf.stale = True
                to_update.append(sf)

        with transaction.atomic():
            if to_create:
                SchemaField.objects.bulk_create(to_create)
            if to_update:
                SchemaField.objects.bulk_update(
                    to_update,
                    fields=["inferred_type", "null_percentage", "sample_value", "stale"],
                )

        created_count = len(to_create)
        stale_count = sum(1 for sf in to_update if sf.stale)
        logger.info(
            "upsert_fields: endpoint=%s created=%d updated=%d stale=%d",
            getattr(endpoint, "pk", None),
            created_count,
            len(to_update) - stale_count,
            stale_count,
        )

        return list(SchemaField.objects.filter(endpoint=endpoint).order_by("key_path"))