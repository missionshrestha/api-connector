// frontend/src/features/endpoint/api/paginationApi.ts
import { apiClient } from "@/lib";
import type { PaginationConfig } from "@/shared/types";

export interface PaginationConfigUpdateRequest {
  strategy: string;
  strategy_params: Record<string, unknown>;
  max_pages?: number;
  max_records?: number;
  inter_page_delay_ms?: number;
  max_retries?: number;
}

export const paginationApi = {
  getPaginationConfig(
    profileId: number,
    endpointId: number,
  ): Promise<PaginationConfig> {
    return apiClient
      .get<PaginationConfig>(
        `/api/connector/profiles/${profileId}/endpoints/${endpointId}/pagination/`,
      )
      .then((r) => r.data);
  },

  updatePaginationConfig(
    profileId: number,
    endpointId: number,
    data: PaginationConfigUpdateRequest,
  ): Promise<PaginationConfig> {
    return apiClient
      .patch<PaginationConfig>(
        `/api/connector/profiles/${profileId}/endpoints/${endpointId}/pagination/`,
        data,
      )
      .then((r) => r.data);
  },
};