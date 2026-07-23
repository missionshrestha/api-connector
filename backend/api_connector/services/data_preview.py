# backend/api_connector/services/data_preview.py
"""
DataPreviewService — fetches, selects, and alias-renames live API records.

Architecture:
  This service is the only place that reads SchemaField.include and SchemaField.alias
  for data retrieval purposes. It is the consumer of:
    - PaginationEngine.paginate() generator (Phase 5 — yields (records, body) tuples after P7.A-01)
    - get_at_path() utility (Phase 5 — nested dot-notation extraction)
    - SchemaField queryset (Phase 6 — provides field selection and alias mapping)

Row limit contract:
  DataPreviewService requests row_limit + 1 records from the engine.
  If engine returns > row_limit: has_more=True, rows trimmed to row_limit.
  If engine returns ≤ row_limit: has_more=False.
  This is the ONLY correct way to detect pagination availability without over-fetching.

Security (OWASP A02/A09):
  - credentials passed through — never log
  - rows and raw_response_body may contain PII — never log values
  - Log only structural metadata: endpoint_id, row_limit, rows_returned, has_more, columns
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from api_connector.models import PaginationConfig, ResponseFormat, SchemaField
from api_connector.services.auth.base import BaseAuthHandler
from api_connector.services.pagination.engine import PaginationEngine
from api_connector.services.pagination.registry import pagination_registry
from api_connector.services.pagination.strategies import (
    NoPaginationStrategy,
    get_at_path,
)
from api_connector.services.pagination.types import SafetyConfig

logger = logging.getLogger("api_connector.data_preview")


# ─── Output types ──────────────────────────────────────────────────────────────


@dataclass
class ColumnMeta:
    """Metadata for one column in the preview result."""

    name: str  # display name: alias if set, else key_path — matches row dict keys
    key_path: str  # original dot-notation path
    effective_type: str  # type_override if set, else inferred_type
    null_percentage: float
    sample_value: Any  # may be PII — never log


@dataclass
class PreviewResult:
    """Complete result of a DataPreviewService.preview() call."""

    rows: list[dict]  # each dict: {column.name: value}
    columns: list[ColumnMeta]  # ordered identically to rows' keys
    raw_response_body: str  # JSON-stringified last page body, truncated at 50,000 chars
    total_fetched: int  # actual rows returned (≤ row_limit)
    has_more: bool  # True when more records exist beyond row_limit


# ─── Exception ────────────────────────────────────────────────────────────────


class PreviewNoFieldsError(Exception):
    """
    Raised when no include=True SchemaFields exist for the endpoint.
    Returned as HTTP 422 (not 500) — the user must go fix their field selection.
    """


# ─── Service ──────────────────────────────────────────────────────────────────


class DataPreviewService:
    """
    Stateless preview service. preview() is the only public method.
    """

    def preview(
        self,
        endpoint: Any,
        auth_handler: BaseAuthHandler,
        credentials: dict,
        row_limit: int,
    ) -> PreviewResult:
        """
        Fetch live API data applying schema field selection and alias mapping.

        Args:
            endpoint: Endpoint model instance. Must have .connection_profile,
                      .data_root_path, .path, .path_variables, .query_params,
                      .endpoint_headers, and optionally .pagination_config.
            auth_handler: Injects credentials into each outbound request.
            credentials: Decrypted credentials dict (must include _profile_id).
            row_limit: Maximum number of rows to return (1–100, validated by serializer).

        Returns:
            PreviewResult with rows, columns, raw_response_body, total_fetched, has_more.

        Raises:
            PreviewNoFieldsError: zero include=True SchemaFields for this endpoint.
            HTTPStatusError, HTTPTimeoutError, HTTPNetworkError: propagated from engine.
        """

        start = time.monotonic()

        # ── Step 1: Load included fields ──────────────────────────────────────
        included_fields = list(
            SchemaField.objects.filter(endpoint=endpoint, include=True).order_by(
                "key_path"
            )
        )
        if not included_fields:
            raise PreviewNoFieldsError(
                "No fields are marked for inclusion. Go to the Schema Explorer "
                "and include at least one field before running a preview."
            )

        # ── Step 2: Build alias_map and columns list ───────────────────────────
        alias_map: dict[str, str] = {}  # {key_path: display_name}
        columns: list[ColumnMeta] = []

        for sf in included_fields:
            display_name = sf.alias if sf.alias else sf.key_path
            alias_map[sf.key_path] = display_name
            columns.append(
                ColumnMeta(
                    name=display_name,
                    key_path=sf.key_path,
                    effective_type=sf.type_override
                    if sf.type_override
                    else sf.inferred_type,
                    null_percentage=sf.null_percentage,
                    sample_value=sf.sample_value,
                )
            )

        # Defensive: warn on alias collisions (should not occur after Phase 6 uniqueness check)
        display_names = list(alias_map.values())
        if len(set(display_names)) < len(display_names):
            logger.warning(
                "DataPreview: duplicate display names detected for endpoint=%s — "
                "later rows will overwrite earlier ones for colliding column name. "
                "Fix aliases in Schema Explorer.",
                getattr(endpoint, "pk", None),
            )

        # ── Step 3: Configure pagination strategy ─────────────────────────────
        try:
            config = endpoint.pagination_config
            strategy = pagination_registry.get(
                config.strategy, params=config.strategy_params or {}
            )
            safety = SafetyConfig(
                max_pages=config.max_pages,
                max_records=config.max_records,
                inter_page_delay_ms=config.inter_page_delay_ms,
                max_retries=config.max_retries,
            )
        except PaginationConfig.DoesNotExist:
            strategy = NoPaginationStrategy()
            safety = SafetyConfig(max_pages=1, max_records=row_limit + 1)

        # ── Step 4: Paginate — request row_limit + 1 to detect has_more ───────
        # Requesting one extra record lets us know more data exists without fetching it.
        all_raw_records: list[dict] = []
        last_raw_body: dict = {}
        raw_response_sink: dict = {}

        engine = PaginationEngine()
        for page_records, raw_body in engine.paginate(
            endpoint=endpoint,
            auth_handler=auth_handler,
            credentials=credentials,
            strategy=strategy,
            safety=safety,
            row_limit=row_limit + 1,
            raw_response_sink=raw_response_sink,
        ):
            all_raw_records.extend(page_records)
            last_raw_body = raw_body

        # ── Step 5: Detect has_more and trim ──────────────────────────────────
        has_more = len(all_raw_records) > row_limit
        raw_records_to_process = all_raw_records[:row_limit]

        # ── Step 6: Extract and alias-rename values per row ───────────────────
        rows: list[dict] = []
        for raw_record in raw_records_to_process:
            row: dict = {}
            for sf in included_fields:
                value = get_at_path(raw_record, sf.key_path)
                column_name = alias_map[sf.key_path]
                row[column_name] = value
            rows.append(row)

        # ── Step 7: Serialize raw_response_body — truncated at 50,000 chars ──
        # XML endpoints show the original response text, not a JSON reinterpretation
        # of the normalized body (DEC-6) — every other consumer above is unaffected.
        if (
            endpoint.response_format == ResponseFormat.XML
            and raw_response_sink.get("text") is not None
        ):
            raw_response_body = raw_response_sink["text"][:50_000]
        else:
            # default=str handles datetimes and other non-JSON-serializable types
            raw_response_body = json.dumps(last_raw_body, indent=2, default=str)[
                :50_000
            ]

        duration_ms = int((time.monotonic() - start) * 1000)
        # Log ONLY structural metadata — never log rows, raw_response_body, or credentials
        logger.info(
            "DataPreview: endpoint=%s row_limit=%d rows_returned=%d has_more=%s "
            "columns=%d duration_ms=%d",
            getattr(endpoint, "pk", None),
            row_limit,
            len(rows),
            has_more,
            len(columns),
            duration_ms,
        )

        return PreviewResult(
            rows=rows,
            columns=columns,
            raw_response_body=raw_response_body,
            total_fetched=len(rows),
            has_more=has_more,
        )
