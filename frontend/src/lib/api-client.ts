// frontend/src/lib/api-client.ts
import axios from "axios";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30_000, // 30 seconds; override per-call as needed
});

// TODO Phase 1: Add response interceptor to normalize APIError envelope
// apiClient.interceptors.response.use(
//   (response) => response,
//   (error) => Promise.reject(normalizeAPIError(error))
// )

// TODO Phase 2+: Add request interceptor for authentication headers.
// Do NOT set default Authorization headers here — they would leak into
// unauthenticated calls (health check, OAuth initiation, etc.).

export default apiClient;