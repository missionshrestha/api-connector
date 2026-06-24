# backend/api_connector/services/schema_inference/types.py
"""
Types and sentinels for the SchemaInferenceEngine.

ARRAY_OF_OBJECTS_SENTINEL and ARRAY_OF_PRIMITIVES_SENTINEL are marker strings
stored in the per-path value lists so _infer_type_from_values() can identify
them by identity check. They use the '__schema_' prefix to guarantee they cannot
naturally appear as API response string values.

Security: SchemaFieldSpec.sample_value holds a raw API response value — may
contain PII. Never log SchemaFieldSpec instances directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ── Sentinel strings ──────────────────────────────────────────────────────────

ARRAY_OF_OBJECTS_SENTINEL: str = "__schema_aoo__"
ARRAY_OF_PRIMITIVES_SENTINEL: str = "__schema_aop__"


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class SchemaFieldSpec:
    """
    Inference result for one discovered field path.
    Returned by SchemaInferenceEngine.infer() — one instance per unique key_path.
    """

    key_path: str
    inferred_type: str        # One of InferredType string values
    null_percentage: float    # 0.0–1.0; fraction of records where absent or None
    sample_value: Any         # First non-null, non-sentinel value seen; may be PII


# ── Exception hierarchy ───────────────────────────────────────────────────────

class SchemaInferenceError(Exception):
    """
    Base for all errors raised by SchemaInferenceEngine.
    Message is safe to surface to the user — never contains raw response bodies.
    """


class SchemaInferenceNoRecordsError(SchemaInferenceError):
    """
    Raised when the sample fetch returns zero records after applying data_root_path.
    Returned as HTTP 422 from the schema_infer action (not a server error —
    it is actionable by the user: fix data_root_path or check the endpoint).
    """