// frontend/src/features/data-preview/hooks/usePreview.ts
import { useMutation } from "@tanstack/react-query";
import { previewApi } from "../api/previewApi";
import type { PreviewResult } from "../types";

/**
 * Mutation hook for triggering a live data preview fetch.
 *
 * Why useMutation and NOT useQuery:
 *   Preview is user-triggered (button click), not auto-fetched.
 *   useQuery would refetch on window focus — undesirable for a live API call
 *   that may have rate-limit or cost implications.
 *
 * retry: 0 — prevents auto-retry on slow APIs. A 10-second response must
 * not automatically fire a second request while the first is in flight.
 */
export function usePreview(profileId: number, endpointId: number) {
  return useMutation<PreviewResult, unknown, number>({
    mutationFn: (rowLimit: number) =>
      previewApi.fetchPreview(profileId, endpointId, rowLimit),
    retry: 0,
  });
}