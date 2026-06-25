// frontend/src/features/data-preview/types/preview.ts
import type { InferredType } from "@/shared/types";

export interface PreviewColumnMeta {
  name: string;           // alias if set, else key_path — the display name AND row dict key
  key_path: string;       // original dot-notation path
  effective_type: InferredType;   // type_override if set, else inferred_type
  null_percentage: number;        // 0.0–1.0
  sample_value: unknown;          // may be PII — unknown forces type narrowing before use
}

export interface PreviewResult {
  rows: Array<Record<string, unknown>>;   // keys are PreviewColumnMeta.name values
  columns: PreviewColumnMeta[];
  raw_response_body: string;              // last page's JSON, may be truncated at 50KB
  total_fetched: number;
  has_more: boolean;
}