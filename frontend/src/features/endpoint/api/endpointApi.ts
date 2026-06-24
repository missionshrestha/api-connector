// frontend/src/features/endpoint/api/endpointApi.ts
import { apiClient } from "@/lib";
import type { Endpoint } from "@/shared/types";

export interface EndpointCreateRequest {
  name: string;
  path: string;
  method: "GET" | "POST";
  query_params?: Array<{ key: string; value: string }>;
  path_variables?: Record<string, string>;
  request_body?: Record<string, unknown> | null;
  endpoint_headers?: Array<{ name: string; value: string }>;
  data_root_path?: string | null;
  record_count_path?: string | null;
}

export type EndpointUpdateRequest = Partial<EndpointCreateRequest>;

export interface DetectDataRootResponse {
  top_candidate: string | null;
  all_candidates: string[];
}

export const endpointApi = {
  listEndpoints(profileId: number): Promise<Endpoint[]> {
    return apiClient
      .get<Endpoint[]>(`/api/connector/profiles/${profileId}/endpoints/`)
      .then((r) => r.data);
  },

  getEndpoint(profileId: number, endpointId: number): Promise<Endpoint> {
    return apiClient
      .get<Endpoint>(`/api/connector/profiles/${profileId}/endpoints/${endpointId}/`)
      .then((r) => r.data);
  },

  createEndpoint(profileId: number, data: EndpointCreateRequest): Promise<Endpoint> {
    return apiClient
      .post<Endpoint>(`/api/connector/profiles/${profileId}/endpoints/`, data)
      .then((r) => r.data);
  },

  updateEndpoint(
    profileId: number,
    endpointId: number,
    data: EndpointUpdateRequest,
  ): Promise<Endpoint> {
    return apiClient
      .patch<Endpoint>(
        `/api/connector/profiles/${profileId}/endpoints/${endpointId}/`,
        data,
      )
      .then((r) => r.data);
  },

  deleteEndpoint(profileId: number, endpointId: number): Promise<void> {
    return apiClient
      .delete(`/api/connector/profiles/${profileId}/endpoints/${endpointId}/`)
      .then(() => undefined);
  },

  detectDataRoot(
    profileId: number,
    endpointId: number,
  ): Promise<DetectDataRootResponse> {
    return apiClient
      .post<DetectDataRootResponse>(
        `/api/connector/profiles/${profileId}/endpoints/${endpointId}/detect-data-root/`,
      )
      .then((r) => r.data);
  },
};