// frontend/src/shared/types/domain.ts

// ── Enum mirrors ──────────────────────────────────────────────────────────────
export type AuthType =
  | "none"
  | "api_key"
  | "bearer"
  | "basic"
  | "oauth_cc"
  | "oauth_ac";

export type PaginationStrategy =
  | "no_pagination"
  | "offset_limit"
  | "page_size"
  | "cursor"
  | "next_url"
  | "link_header";

export type InferredType =
  | "null"
  | "boolean"
  | "integer"
  | "float"
  | "date"
  | "datetime"
  | "string"
  | "mixed"
  | "array_of_objects"
  | "array_of_primitives";

export type ArrayHandling = "expand" | "retain";

export type HTTPMethod = "GET" | "POST";

export type ResponseFormat = "json" | "xml";

// ── Phase 2 read shape ────────────────────────────────────────────────────────
// credentials_summary is returned by Phase 2 serializer; never the raw credentials.
export interface CredentialsSummary {
  [fieldKey: string]: { is_set: boolean };
}

// ── Domain entities (read shapes — what the API returns) ──────────────────────

export interface ConnectionProfile {
  id: number;
  name: string;
  base_url: string;
  auth_type: AuthType;
  default_headers: Array<{ name: string; value: string }>;
  ssl_verify: boolean;
  request_timeout: number;
  last_test_at: string | null;
  last_test_outcome: boolean | null;
  last_test_status_code: number | null;
  last_test_response_time: number | null;
  last_test_detected_format: string | null;
  credentials_summary: CredentialsSummary | null;
  oauth_ac_authorized: boolean | null; // null for non-OAuth-AC profiles  ← ADD THIS
  created_at: string;
  updated_at: string;
}

export interface Endpoint {
  id: number;
  connection_profile: number; // FK id
  name: string;
  path: string;
  method: HTTPMethod;
  query_params: Array<{ key: string; value: string }>;
  path_variables: Record<string, string>;
  request_body: Record<string, unknown> | null;
  endpoint_headers: Array<{ name: string; value: string }>;
  response_format: ResponseFormat;
  data_root_path: string | null;
  record_count_path: string | null;
  detected_path_variables: string[];       // computed at read time
  has_pagination_config: boolean;           // computed from OneToOne relation
  created_at: string;
  updated_at: string;
}

export interface PaginationConfig {
  id: number;
  endpoint: number; // FK id
  strategy: PaginationStrategy;
  strategy_params: Record<string, unknown>;
  max_pages: number;
  max_records: number;
  inter_page_delay_ms: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
}

export interface SchemaField {
  id: number;
  endpoint: number;
  key_path: string;
  alias: string | null;
  inferred_type: InferredType;
  type_override: InferredType | null;
  include: boolean;
  array_handling: ArrayHandling | null;
  null_percentage: number;    // 0.0–1.0
  sample_value: unknown;      // unknown (not any) — caller must narrow before use
  stale: boolean;             // true = path absent from latest inference sample
  created_at: string;
  updated_at: string;
}

export interface StepResult {
  name: string;
  passed: boolean;
  message: string;
  detail: Record<string, unknown>;
}

export interface ConnectionTestResult {
  id: number;
  connection_profile: number;
  tested_at: string;
  step_results: StepResult[];
  overall_passed: boolean;
  test_path: string | null;
  duration_ms: number | null;
}