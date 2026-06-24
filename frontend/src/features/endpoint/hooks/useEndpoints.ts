// frontend/src/features/endpoint/hooks/useEndpoints.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpointApi, paginationApi } from "../api";
import type { EndpointCreateRequest, EndpointUpdateRequest } from "../api/endpointApi";
import type { PaginationConfigUpdateRequest } from "../api/paginationApi";

/**
 * Query key FUNCTION — ensures profile-scoped cache isolation.
 * Invalidating ENDPOINT_QUERY_KEY(2) does NOT flush ENDPOINT_QUERY_KEY(1).
 */
export const ENDPOINT_QUERY_KEY = (profileId: number) =>
  ["endpoints", profileId] as const;

export function useEndpoints(profileId: number) {
  return useQuery({
    queryKey: ENDPOINT_QUERY_KEY(profileId),
    queryFn: () => endpointApi.listEndpoints(profileId),
    enabled: !!profileId,
  });
}

export function useEndpoint(profileId: number, endpointId?: number) {
  return useQuery({
    queryKey: [...ENDPOINT_QUERY_KEY(profileId), endpointId],
    queryFn: () => endpointApi.getEndpoint(profileId, endpointId!),
    enabled: !!profileId && !!endpointId,
  });
}

export function useCreateEndpoint(profileId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: EndpointCreateRequest) =>
      endpointApi.createEndpoint(profileId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENDPOINT_QUERY_KEY(profileId) });
    },
  });
}

export function useUpdateEndpoint(profileId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ endpointId, data }: { endpointId: number; data: EndpointUpdateRequest }) =>
      endpointApi.updateEndpoint(profileId, endpointId, data),
    onSuccess: (_, { endpointId }) => {
      queryClient.invalidateQueries({ queryKey: ENDPOINT_QUERY_KEY(profileId) });
      queryClient.invalidateQueries({
        queryKey: [...ENDPOINT_QUERY_KEY(profileId), endpointId],
      });
    },
  });
}

export function useDeleteEndpoint(profileId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (endpointId: number) =>
      endpointApi.deleteEndpoint(profileId, endpointId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENDPOINT_QUERY_KEY(profileId) });
    },
  });
}

export function usePaginationConfig(profileId: number, endpointId?: number) {
  return useQuery({
    queryKey: ["pagination-config", profileId, endpointId],
    queryFn: () => paginationApi.getPaginationConfig(profileId, endpointId!),
    enabled: !!profileId && !!endpointId,
  });
}

export function useUpdatePaginationConfig(profileId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      endpointId,
      data,
    }: {
      endpointId: number;
      data: PaginationConfigUpdateRequest;
    }) => paginationApi.updatePaginationConfig(profileId, endpointId, data),
    onSuccess: (_, { endpointId }) => {
      queryClient.invalidateQueries({
        queryKey: ["pagination-config", profileId, endpointId],
      });
    },
  });
}

export function useDetectDataRoot(profileId: number) {
  return useMutation({
    mutationFn: (endpointId: number) =>
      endpointApi.detectDataRoot(profileId, endpointId),
  });
}