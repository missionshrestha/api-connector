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