// frontend/src/features/connection-profile/api/profilesApi.ts
import { apiClient } from "@/lib";
import type { ConnectionProfile } from "@/shared/types";
import type { ProfileCreateRequest, ProfileUpdateRequest } from "../types";

/**
 * API functions for /api/connector/profiles/.
 *
 * IMPORTANT: listProfiles returns ConnectionProfile[] — a plain array.
 * DRF pagination is NOT configured on this endpoint (no PaginatedResponse wrapper).
 * Do NOT type the return as PaginatedResponse<ConnectionProfile>.
 */

export const profilesApi = {
  listProfiles(search?: string): Promise<ConnectionProfile[]> {
    const params = search ? { search: search.trim() } : undefined;
    return apiClient.get<ConnectionProfile[]>("/api/connector/profiles/", { params })
      .then((r) => r.data);
  },

  getProfile(id: number): Promise<ConnectionProfile> {
    return apiClient.get<ConnectionProfile>(`/api/connector/profiles/${id}/`)
      .then((r) => r.data);
  },

  createProfile(data: ProfileCreateRequest): Promise<ConnectionProfile> {
    return apiClient.post<ConnectionProfile>("/api/connector/profiles/", data)
      .then((r) => r.data);
  },

  updateProfile(id: number, data: ProfileUpdateRequest): Promise<ConnectionProfile> {
    return apiClient.patch<ConnectionProfile>(`/api/connector/profiles/${id}/`, data)
      .then((r) => r.data);
  },

  deleteProfile(id: number): Promise<void> {
    return apiClient.delete(`/api/connector/profiles/${id}/`).then(() => undefined);
  },
};