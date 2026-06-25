// frontend/src/features/data-preview/api/previewApi.ts
import { apiClient } from "@/lib";
import type { PreviewResult } from "../types";

export const previewApi = {
  /**
   * Fetch a live data preview for the endpoint.
   * row_limit: 1–100 (validated server-side). Default 25.
   *
   * This call is synchronous server-side and may take up to 10 seconds.
   * Use with useMutation (not useQuery) — preview is user-triggered, not auto-fetched.
   */
  fetchPreview(
    profileId: number,
    endpointId: number,
    rowLimit: number,
  ): Promise<PreviewResult> {
    return apiClient
      .post<PreviewResult>(
        `/api/connector/profiles/${profileId}/endpoints/${endpointId}/preview/`,
        { row_limit: rowLimit },
      )
      .then((r) => r.data);
  },
};