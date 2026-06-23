// frontend/src/features/connection-profile/types/connectionTest.ts

export type StepName =
  | "dns_resolution"
  | "network_connectivity"
  | "auth_injection"
  | "http_response"
  | "format_detection"
  | "response_sample";

export const STEP_DISPLAY_NAMES: Record<StepName, string> = {
  dns_resolution: "DNS Resolution",
  network_connectivity: "Network Connectivity",
  auth_injection: "Auth Injection",
  http_response: "HTTP Response",
  format_detection: "Format Detection",
  response_sample: "Response Sample",
};

export const ALL_STEP_NAMES: StepName[] = [
  "dns_resolution",
  "network_connectivity",
  "auth_injection",
  "http_response",
  "format_detection",
  "response_sample",
];

export interface TestStepResult {
  name: StepName;
  passed: boolean;
  message: string;
  detail: Record<string, unknown>;
  duration_ms?: number;
}

export interface ConnectionTestResult {
  result_id: number;
  overall_passed: boolean;
  tested_at: string; // ISO 8601
  duration_ms: number;
  steps: TestStepResult[];
}

// ── OAuth AC postMessage event types ──────────────────────────────────────────

export interface OAuthACSuccessEvent {
  type: "OAUTH_AC_SUCCESS";
  profileId: number;
}

export interface OAuthACErrorEvent {
  type: "OAUTH_AC_ERROR";
  message: string;
}

export type OAuthACMessageEvent = OAuthACSuccessEvent | OAuthACErrorEvent;

export type OAuthACStatus =
  | "unauthorized"   // No token in DB; Authorize button visible
  | "authorizing"    // Popup open, waiting for postMessage
  | "authorized"     // Token in DB and not expired; "Authorized ✓" badge shown
  | "expired";       // Token expired and refresh failed; re-authorize prompt