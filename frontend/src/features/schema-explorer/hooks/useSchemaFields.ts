// frontend/src/features/schema-explorer/hooks/useSchemaFields.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { SchemaField } from "@/shared/types";
import {
  schemaApi,
  type BulkUpdateSchemaFieldsRequest,
  type UpdateSchemaFieldRequest,
} from "../api/schemaApi";

/**
 * Query key FUNCTION — per-endpoint cache isolation.
 * Invalidating SCHEMA_QUERY_KEY(1, 2) does NOT flush SCHEMA_QUERY_KEY(1, 3).
 */
export const SCHEMA_QUERY_KEY = (profileId: number, endpointId: number) =>
  ["schema-fields", profileId, endpointId] as const;

export function useSchemaFields(profileId: number, endpointId: number | undefined) {
  return useQuery({
    queryKey: SCHEMA_QUERY_KEY(profileId, endpointId ?? 0),
    queryFn: () => schemaApi.listFields(profileId, endpointId!),
    enabled: !!profileId && !!endpointId,
    staleTime: 60_000, // Schema rarely changes spontaneously
  });
}

export function useRunInference(profileId: number, endpointId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => schemaApi.runInference(profileId, endpointId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SCHEMA_QUERY_KEY(profileId, endpointId) });
    },
  });
}

export function useUpdateSchemaField(profileId: number, endpointId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      fieldId,
      data,
    }: {
      fieldId: number;
      data: UpdateSchemaFieldRequest;
    }) => schemaApi.updateField(profileId, endpointId, fieldId, data),

    // Optimistic update — makes alias blur-save feel instant
    onMutate: async ({ fieldId, data }) => {
      await queryClient.cancelQueries({
        queryKey: SCHEMA_QUERY_KEY(profileId, endpointId),
      });
      const previous = queryClient.getQueryData<SchemaField[]>(
        SCHEMA_QUERY_KEY(profileId, endpointId),
      );
      queryClient.setQueryData<SchemaField[]>(
        SCHEMA_QUERY_KEY(profileId, endpointId),
        (old) =>
          old?.map((f) =>
            f.id === fieldId ? ({ ...f, ...data } as SchemaField) : f,
          ) ?? [],
      );
      return { previous };
    },

    onError: (_err, _vars, context) => {
      // Roll back on error
      if (context?.previous) {
        queryClient.setQueryData(
          SCHEMA_QUERY_KEY(profileId, endpointId),
          context.previous,
        );
      }
    },

    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: SCHEMA_QUERY_KEY(profileId, endpointId),
      });
    },
  });
}

export function useBulkUpdateSchemaFields(profileId: number, endpointId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: BulkUpdateSchemaFieldsRequest) =>
      schemaApi.bulkUpdateFields(profileId, endpointId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SCHEMA_QUERY_KEY(profileId, endpointId) });
    },
  });
}