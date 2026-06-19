// frontend/src/shared/types/api.ts

export interface APIError {
  error_code: string;
  message: string;
  detail: Record<string, unknown> | unknown[]; // never null
}

// DRF paginated list response shape
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}