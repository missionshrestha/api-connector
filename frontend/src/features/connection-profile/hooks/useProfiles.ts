// frontend/src/features/connection-profile/hooks/useProfiles.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "../api/profilesApi";
import type { ProfileCreateRequest, ProfileUpdateRequest } from "../types";

/**
 * Base query key for all profile queries.
 * Using a base key + queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY })
 * invalidates ALL queries whose key starts with ['profiles'] — list, detail, search variants.
 */
export const PROFILE_QUERY_KEY = ["profiles"] as const;

/**
 * Fetch all profiles, optionally filtered by name search.
 * Query key includes search so different searches are cached separately.
 */
export function useProfiles(search?: string) {
  return useQuery({
    queryKey: [...PROFILE_QUERY_KEY, search ?? ""],
    queryFn: () => profilesApi.listProfiles(search),
    staleTime: 30_000,
  });
}

/**
 * Fetch a single profile by id.
 * Pass undefined to skip fetching (create mode).
 */
export function useProfile(id?: number) {
  return useQuery({
    queryKey: [...PROFILE_QUERY_KEY, id],
    queryFn: () => profilesApi.getProfile(id!),
    enabled: id !== undefined,
  });
}

export function useCreateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ProfileCreateRequest) => profilesApi.createProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ProfileUpdateRequest }) =>
      profilesApi.updateProfile(id, data),
    onSuccess: (_, { id }) => {
      // Invalidate list and the specific detail query
      queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: [...PROFILE_QUERY_KEY, id] });
    },
  });
}

export function useDeleteProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => profilesApi.deleteProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
    },
  });
}