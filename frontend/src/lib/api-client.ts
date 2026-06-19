// frontend/src/lib/api-client.ts
import axios from "axios";
import type { AxiosError } from "axios";
import type { APIError } from "@/shared/types";
import { ErrorCode } from "@/lib/errors";

/**
 * Type guard: checks if an unknown value has the APIError envelope shape.
 * Used by the Axios interceptor to decide whether to forward the error as-is
 * or wrap it in a synthetic APIError.
 */
function isAPIError(data: unknown): data is APIError {
  return (
    typeof data === "object" &&
    data !== null &&
    "error_code" in data &&
    "message" in data &&
    "detail" in data
  );
}

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30_000, // 30 seconds; override per-call via config.timeout
});

// ── Response interceptor: normalize ALL errors to APIError shape ──────────────
apiClient.interceptors.response.use(
  // Success path: return the response unchanged
  (response) => response,

  // Error path: normalize to APIError
  (error: unknown) => {
    const axiosError = error as AxiosError<APIError>;

    if (axiosError.response?.data && isAPIError(axiosError.response.data)) {
      // Backend returned the structured envelope — forward it directly
      return Promise.reject(axiosError.response.data);
    }

    // Network error, timeout, or malformed response — return synthetic APIError
    return Promise.reject({
      error_code: ErrorCode.UNEXPECTED_ERROR,
      message: "A network error occurred. Please check your connection.",
      detail: {},
    } satisfies APIError);
  },
);

// TODO Phase 2+: Add request interceptor for authentication headers.
// Do NOT set default Authorization headers here — they would leak into
// unauthenticated calls (health check, OAuth initiation, etc.).

export default apiClient;