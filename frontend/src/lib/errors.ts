// frontend/src/lib/errors.ts
// Mirrors backend/api_connector/error_codes.py exactly.
// When adding a new error code: update error_codes.py FIRST, then this file.

export const ErrorCode = {
  // Core validation
  VALIDATION_ERROR: "API_CONN_001",
  NOT_FOUND: "API_CONN_002",
  PERMISSION_DENIED: "API_CONN_003",

  // Profile errors
  PROFILE_NOT_FOUND: "API_CONN_010",
  PROFILE_NAME_CONFLICT: "API_CONN_011",
  CREDENTIAL_ENCRYPTION_FAILED: "API_CONN_012",

  // Endpoint errors
  ENDPOINT_NOT_FOUND: "API_CONN_020",
  ENDPOINT_INVALID_PATH: "API_CONN_021",

  // Connection test errors
  TEST_DNS_FAILURE: "API_CONN_030",
  TEST_NETWORK_FAILURE: "API_CONN_031",
  TEST_AUTH_FAILURE: "API_CONN_032",
  TEST_HTTP_FAILURE: "API_CONN_033",
  TEST_TIMEOUT: "API_CONN_034",
  TEST_FORMAT_DETECTION_FAILED: "API_CONN_035",

  // OAuth errors
  OAUTH_CC_TOKEN_FETCH_FAILED: "API_CONN_040",
  OAUTH_AC_REAUTHORIZATION_REQUIRED: "API_CONN_041",
  OAUTH_AC_STATE_EXPIRED: "API_CONN_042",

  // Schema and preview errors
  SCHEMA_INFERENCE_FAILED: "API_CONN_050",
  SCHEMA_INFERENCE_NO_RECORDS: "API_CONN_051",
  DATA_ROOT_PATH_INVALID: "API_CONN_052",
  PREVIEW_FETCH_FAILED: "API_CONN_053",
  ALIAS_DUPLICATE: "API_CONN_054",

  // Internal
  ENCRYPTION_KEY_MISSING: "API_CONN_090",
  UNEXPECTED_ERROR: "API_CONN_099",
} as const;

// Derive the union type of all possible error code values
export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];