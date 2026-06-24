// frontend/src/features/schema-explorer/api/schemaApi.ts
import { apiClient } from "@/lib";
import type { SchemaField } from "@/shared/types";

export interface UpdateSchemaFieldRequest {
  alias?: string | null;
  include?: boolean;
  type_override?: string | null;
  array_handling?: string | null;
}

export interface BulkUpdateSchemaFieldsRequest {
  include_all?: boolean;
  field_ids?: number[];
  include?: boolean;
}

export interface BulkUpdateResponse {
  updated_count: number;
}

const base = (profileId: number, endpointId: number) =>
  `/api/connector/profiles/${profileId}/endpoints/${endpointId}`;

export const schemaApi = {
  runInference(profileId: number, endpointId: number): Promise<SchemaField[]> {
    return apiClient
      .post<SchemaField[]>(`${base(profileId, endpointId)}/schema/infer/`)
      .then((r) => r.data);
  },

  listFields(profileId: number, endpointId: number): Promise<SchemaField[]> {
    return apiClient
      .get<SchemaField[]>(`${base(profileId, endpointId)}/schema/fields/`)
      .then((r) => r.data);
  },

  updateField(
    profileId: number,
    endpointId: number,
    fieldId: number,
    data: UpdateSchemaFieldRequest,
  ): Promise<SchemaField> {
    return apiClient
      .patch<SchemaField>(
        `${base(profileId, endpointId)}/schema/fields/${fieldId}/`,
        data,
      )
      .then((r) => r.data);
  },

  bulkUpdateFields(
    profileId: number,
    endpointId: number,
    data: BulkUpdateSchemaFieldsRequest,
  ): Promise<BulkUpdateResponse> {
    return apiClient
      .post<BulkUpdateResponse>(
        `${base(profileId, endpointId)}/schema/fields/bulk-update/`,
        data,
      )
      .then((r) => r.data);
  },
};