// frontend/src/features/data-preview/pages/DataPreviewPage.tsx
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import type { APIError } from "@/shared/types";
import { useEndpoint } from "@/features/endpoint/hooks";
import { useSchemaFields } from "@/features/schema-explorer/hooks";
import { usePreview } from "../hooks";
import { DataPreviewTable, ExportButtons, RawResponseViewer } from "../components";

const DEFAULT_ROW_LIMIT = 25;

export default function DataPreviewPage() {
  const { profileId: profileIdStr, endpointId: endpointIdStr } = useParams<{
    profileId: string;
    endpointId: string;
  }>();

  const profileId = Number(profileIdStr);
  const endpointId = Number(endpointIdStr);

  const [rowLimit, setRowLimit] = useState(DEFAULT_ROW_LIMIT);
  const [showRawResponse, setShowRawResponse] = useState(false);

  const { data: endpoint, isLoading: isLoadingEndpoint } = useEndpoint(
    profileId,
    endpointId,
  );

  // Schema fields for the inclusion count indicator
  const { data: schemaFields } = useSchemaFields(profileId, endpointId);
  const includedFieldCount = schemaFields?.filter((f) => f.include).length ?? 0;
  const totalFieldCount = schemaFields?.length ?? 0;

  const preview = usePreview(profileId, endpointId);

  function handleFetch() {
    setShowRawResponse(false); // reset raw view on new fetch
    preview.mutate(rowLimit);
  }

  function handleRowLimitChange(newLimit: number) {
    setRowLimit(newLimit);
    // CRITICAL: always trigger a new API call when row limit changes
    // Updating state alone shows stale row count without re-fetching
    preview.mutate(newLimit);
  }

  const previewError = preview.error as unknown as APIError | null;

  return (
    <div className="container mx-auto py-8 px-4 max-w-6xl">
      {/* Breadcrumb */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
          <Link
            to={`/profiles/${profileId}/endpoints`}
            className="hover:text-foreground"
          >
            Endpoints
          </Link>
          <span>/</span>
          <Link
            to={`/profiles/${profileId}/endpoints/${endpointId}/schema`}
            className="hover:text-foreground"
          >
            Schema
          </Link>
          <span>/</span>
          <span className="text-foreground">Preview</span>
        </div>

        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold">Data Preview</h1>
            {endpoint && (
              <p className="text-sm text-muted-foreground font-mono mt-0.5">
                {endpoint.name} · {endpoint.path}
              </p>
            )}
          </div>

          {/* Schema field inclusion summary */}
          {totalFieldCount > 0 && (
            <div className="text-sm text-muted-foreground">
              {includedFieldCount} / {totalFieldCount} fields included
              {includedFieldCount === 0 && (
                <Link
                  to={`/profiles/${profileId}/endpoints/${endpointId}/schema`}
                  className="ml-2 text-primary underline"
                >
                  Go to Schema Explorer →
                </Link>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <Button
          onClick={handleFetch}
          disabled={
            preview.isPending || isLoadingEndpoint || includedFieldCount === 0
          }
        >
          {preview.isPending ? "Fetching…" : "Fetch Preview"}
        </Button>

        {/* Raw Response toggle — only when result exists */}
        {preview.data && (
          <Button
            type="button"
            variant="outline"
            onClick={() => setShowRawResponse((v) => !v)}
          >
            {showRawResponse ? "Show Table" : "Raw Response"}
          </Button>
        )}

        {/* Export buttons — only when result exists */}
        {preview.data && endpoint && (
          <ExportButtons result={preview.data} endpointName={endpoint.name} />
        )}
      </div>

      {/* No included fields — amber warning */}
      {includedFieldCount === 0 && totalFieldCount > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800 p-4 mb-4">
          <p className="text-sm text-amber-700 dark:text-amber-300">
            No fields are marked for inclusion. Visit the{" "}
            <Link
              to={`/profiles/${profileId}/endpoints/${endpointId}/schema`}
              className="underline"
            >
              Schema Explorer
            </Link>{" "}
            and include at least one field before previewing.
          </p>
        </div>
      )}

      {/* No schema at all */}
      {totalFieldCount === 0 && !isLoadingEndpoint && (
        <div className="rounded-md border border-dashed border-border p-8 text-center text-muted-foreground mb-4">
          <p className="font-medium mb-1">Schema not yet discovered.</p>
          <p className="text-sm mb-4">
            Run schema inference first so fields can be selected for the preview.
          </p>
          <Button asChild variant="outline">
            <Link to={`/profiles/${profileId}/endpoints/${endpointId}/schema`}>
              Go to Schema Explorer
            </Link>
          </Button>
        </div>
      )}

      {/* Error state */}
      {previewError && !preview.isPending && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-4 mb-4">
          <p className="text-sm text-destructive font-medium">Preview failed</p>
          <p className="text-sm text-destructive/80 mt-1">
            {previewError.message ??
              "An unexpected error occurred. Check the endpoint configuration and try again."}
          </p>
          {previewError.error_code === "API_CONN_051" && (
            <Link
              to={`/profiles/${profileId}/endpoints/${endpointId}/schema`}
              className="text-sm underline text-destructive mt-2 inline-block"
            >
              Go to Schema Explorer to include fields →
            </Link>
          )}
        </div>
      )}

      {/* Loading skeleton */}
      {preview.isPending && (
        <div className="space-y-2">
          <div className="flex gap-2 mb-3">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-8 w-24" />
            ))}
          </div>
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full rounded" />
          ))}
        </div>
      )}

      {/* Result */}
      {!preview.isPending && preview.data && (
        <>
          {showRawResponse ? (
            <RawResponseViewer body={preview.data.raw_response_body} />
          ) : (
            <DataPreviewTable
              result={preview.data}
              rowLimit={rowLimit}
              onRowLimitChange={handleRowLimitChange}
              isRefetching={preview.isPending}
            />
          )}
        </>
      )}
    </div>
  );
}