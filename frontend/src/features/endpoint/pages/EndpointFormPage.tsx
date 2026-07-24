// frontend/src/features/endpoint/pages/EndpointFormPage.tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Separator } from "@/shared/components/ui/separator";
import { Textarea } from "@/shared/components/ui/textarea";
import type { APIError, ResponseFormat } from "@/shared/types";
import { useProfile } from "@/features/connection-profile/hooks";
import { endpointSchema, type EndpointFormValues } from "../schemas/endpointSchema";
import type { PaginationConfigFormValues } from "../schemas/paginationConfigSchema";
import {
  useCreateEndpoint,
  useEndpoint,
  usePaginationConfig,
  useUpdateEndpoint,
  useUpdatePaginationConfig,
} from "../hooks";
import {
  DataRootPathInput,
  EndpointHeadersEditor,
  PathVariableEditor,
  PaginationStrategySelector,
  QueryParamEditor,
} from "../components";

const DEFAULT_PAGINATION: PaginationConfigFormValues = {
  strategy: "no_pagination",
  strategy_params: {},
  max_pages: 100,
  max_records: 10000,
  inter_page_delay_ms: 0,
  max_retries: 3,
};

export default function EndpointFormPage() {
  const { profileId: profileIdStr, endpointId: endpointIdStr } = useParams<{
    profileId: string;
    endpointId?: string;
  }>();
  const navigate = useNavigate();

  const profileId = Number(profileIdStr);
  const endpointId = endpointIdStr ? Number(endpointIdStr) : undefined;
  const isEditMode = !!endpointId;

  const { data: endpoint, isLoading: isLoadingEndpoint } = useEndpoint(
    profileId,
    endpointId,
  );
  const { data: paginationConfig, isLoading: isLoadingPagination } =
    usePaginationConfig(profileId, endpointId);
  const { data: profile } = useProfile(profileId);

  const createEndpoint = useCreateEndpoint(profileId);
  const updateEndpoint = useUpdateEndpoint(profileId);
  const updatePaginationConfig = useUpdatePaginationConfig(profileId);

  const [paginationFormValues, setPaginationFormValues] =
    useState<PaginationConfigFormValues | null>(null);

  const effectivePaginationValues: PaginationConfigFormValues =
    paginationFormValues ??
    (paginationConfig
      ? {
          strategy: paginationConfig.strategy,
          strategy_params: paginationConfig.strategy_params,
          max_pages: paginationConfig.max_pages,
          max_records: paginationConfig.max_records,
          inter_page_delay_ms: paginationConfig.inter_page_delay_ms,
          max_retries: paginationConfig.max_retries,
        }
      : DEFAULT_PAGINATION);

  const {
    control,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting, dirtyFields },
  } = useForm<EndpointFormValues>({
    resolver: zodResolver(endpointSchema),
    defaultValues: {
      name: "",
      path: "",
      method: "GET",
      query_params: [],
      path_variables: {},
      request_body: null,
      endpoint_headers: [],
      response_format: "json",
      data_root_path: null,
      record_count_path: null,
    },
  });

  // Populate form in edit mode
  useEffect(() => {
    if (isEditMode && endpoint) {
      reset({
        name: endpoint.name,
        path: endpoint.path,
        method: endpoint.method,
        query_params: endpoint.query_params,
        path_variables: endpoint.path_variables,
        request_body: endpoint.request_body,
        endpoint_headers: endpoint.endpoint_headers,
        response_format: endpoint.response_format,
        data_root_path: endpoint.data_root_path,
        record_count_path: endpoint.record_count_path,
      });
    }
  }, [endpoint, isEditMode, reset]);

  // Create-mode default: mirror the server-side fallback (views/endpoint.py:116-120)
  // so the Select visibly shows the soon-to-be-actual default before submit. Only
  // exact "json"/"xml" values count; anything else (including a never-tested
  // profile's null) falls back to "json". Never overrides a value the user already
  // touched.
  useEffect(() => {
    if (
      !isEditMode &&
      profile &&
      !dirtyFields.response_format
    ) {
      setValue(
        "response_format",
        profile.last_test_detected_format === "xml" ? "xml" : "json",
      );
    }
  }, [profile, isEditMode, dirtyFields.response_format, setValue]);

  const watchedMethod = useWatch({ control, name: "method" });
  const watchedPath = useWatch({ control, name: "path" });
  const watchedResponseFormat = useWatch({ control, name: "response_format" });

  // Path variables detected from the path field
  const detectedVarNames =
    (watchedPath ?? "").match(/\{(\w+)\}/g)?.map((m) => m.replace(/[{}]/g, "")) ?? [];

  // Clear request_body when switching to GET
  function handleMethodChange(newMethod: string) {
    setValue("method", newMethod as "GET" | "POST");
    if (newMethod === "GET") {
      setValue("request_body", null);
    }
  }

  function handleResponseFormatChange(newFormat: string) {
    setValue("response_format", newFormat as ResponseFormat, { shouldDirty: true });
  }

  async function onSubmit(data: EndpointFormValues) {
    // Step 1: Save endpoint
    if (isEditMode && endpointId) {
      await new Promise<void>((resolve, reject) => {
        updateEndpoint.mutate(
          { endpointId, data },
          { onSuccess: () => resolve(), onError: reject },
        );
      });
    } else {
      await new Promise<void>((resolve, reject) => {
        createEndpoint.mutate(data, {
          onSuccess: () => resolve(),
          onError: reject,
        });
      });
    }

    // Step 2: Save pagination config (always save — upsert)
    const savedEndpointId = endpointId ?? createEndpoint.data?.id;
    if (savedEndpointId) {
      updatePaginationConfig.mutate({
        endpointId: savedEndpointId,
        data: {
          strategy: effectivePaginationValues.strategy,
          strategy_params: effectivePaginationValues.strategy_params,
          max_pages: effectivePaginationValues.max_pages,
          max_records: effectivePaginationValues.max_records,
          inter_page_delay_ms: effectivePaginationValues.inter_page_delay_ms,
          max_retries: effectivePaginationValues.max_retries,
        },
      });
    }

    navigate(`/profiles/${profileId}/endpoints`);
  }

  const isSaving =
    createEndpoint.isPending || updateEndpoint.isPending || isSubmitting;

  const mutationError = isEditMode ? updateEndpoint.error : createEndpoint.error;

  if (isEditMode && (isLoadingEndpoint || isLoadingPagination)) {
    return (
      <div className="container mx-auto py-8 px-4 max-w-2xl">
        Loading endpoint configuration…
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">
          {isEditMode ? `Edit ${endpoint?.name ?? "Endpoint"}` : "New Endpoint"}
        </h1>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} autoComplete="off" className="space-y-8">
        {/* ── Section 1: Endpoint Configuration ─────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-medium border-b pb-2">Endpoint Configuration</h2>

          <Controller
            name="name"
            control={control}
            render={({ field }) => (
              <div className="space-y-1">
                <Label>Name</Label>
                <Input {...field} placeholder="List Users" />
                {errors.name && (
                  <p className="text-destructive text-sm">{errors.name.message}</p>
                )}
              </div>
            )}
          />

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-1">
              <Label>Path</Label>
              <Controller
                name="path"
                control={control}
                render={({ field }) => (
                  <Input {...field} placeholder="/api/v1/items" />
                )}
              />
              {errors.path && (
                <p className="text-destructive text-sm">{errors.path.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <Label>Method</Label>
              <Select value={watchedMethod} onValueChange={handleMethodChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="GET">GET</SelectItem>
                  <SelectItem value="POST">POST</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Path Variables */}
          {detectedVarNames.length > 0 && (
            <div className="space-y-2">
              <Label>Path Variables</Label>
              <Controller
                name="path_variables"
                control={control}
                render={({ field }) => (
                  <PathVariableEditor
                    pathVariables={field.value ?? {}}
                    onChange={field.onChange}
                    detectedNames={
                      endpoint?.detected_path_variables ?? detectedVarNames
                    }
                  />
                )}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label>Query Parameters</Label>
            <Controller
              name="query_params"
              control={control}
              render={({ field }) => (
                <QueryParamEditor
                  value={field.value ?? []}
                  onChange={field.onChange}
                />
              )}
            />
          </div>

          <div className="space-y-2">
            <Label>Endpoint Headers</Label>
            <Controller
              name="endpoint_headers"
              control={control}
              render={({ field }) => (
                <EndpointHeadersEditor
                  value={field.value ?? []}
                  onChange={field.onChange}
                />
              )}
            />
          </div>

          {watchedMethod === "POST" && (
            <Controller
              name="request_body"
              control={control}
              render={({ field }) => (
                <div className="space-y-1">
                  <Label>Request Body (JSON)</Label>
                  <Textarea
                    value={
                      field.value ? JSON.stringify(field.value, null, 2) : ""
                    }
                    onChange={(e) => {
                      try {
                        field.onChange(JSON.parse(e.target.value));
                      } catch {
                        // Let user keep typing invalid JSON
                      }
                    }}
                    placeholder={'{"filter": "value"}'}
                    rows={4}
                  />
                  <p className="text-xs text-muted-foreground">
                    Do not include credentials here — use the profile authentication settings.
                  </p>
                </div>
              )}
            />
          )}

          <div className="space-y-1">
            <Label>Response Format</Label>
            <Select
              value={watchedResponseFormat}
              onValueChange={handleResponseFormatChange}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="json">JSON</SelectItem>
                <SelectItem value="xml">XML</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Data Root Path</Label>
            <p className="text-xs text-muted-foreground">
              Dot-notation path to the array of records (e.g. data.items).
            </p>
            <Controller
              name="data_root_path"
              control={control}
              render={({ field }) => (
                <DataRootPathInput
                  value={field.value ?? null}
                  onChange={field.onChange}
                  profileId={profileId}
                  endpointId={endpointId}
                  isEditMode={isEditMode}
                />
              )}
            />
          </div>
        </section>

        <Separator />

        {/* ── Section 2: Pagination Configuration ───────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-medium border-b pb-2">Pagination Configuration</h2>
          <PaginationStrategySelector
            value={effectivePaginationValues}
            onChange={setPaginationFormValues}
          />
        </section>

        {mutationError && (
          <p className="text-destructive text-sm">
            {(mutationError as unknown as APIError)?.message ??
              "An error occurred. Please try again."}
          </p>
        )}

        <div className="flex gap-3">
          <Button type="submit" disabled={isSaving}>
            {isSaving
              ? "Saving…"
              : isEditMode
                ? "Save Changes"
                : "Create Endpoint"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate(`/profiles/${profileId}/endpoints`)}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}