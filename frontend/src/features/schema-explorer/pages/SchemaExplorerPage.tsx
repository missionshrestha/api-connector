// frontend/src/features/schema-explorer/pages/SchemaExplorerPage.tsx
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Skeleton } from "@/shared/components/ui/skeleton";
import type { APIError } from "@/shared/types";
import {
  useBulkUpdateSchemaFields,
  useRunInference,
  useSchemaFields,
  useUpdateSchemaField,
} from "../hooks";
import {
  RerunInferenceDialog,
  SchemaExplorerTree,
} from "../components";
import { useEndpoint } from "@/features/endpoint/hooks";

export default function SchemaExplorerPage() {
  const { profileId: profileIdStr, endpointId: endpointIdStr } = useParams<{
    profileId: string;
    endpointId: string;
  }>();
  const navigate = useNavigate();

  const profileId = Number(profileIdStr);
  const endpointId = Number(endpointIdStr);

  const { data: endpoint } = useEndpoint(profileId, endpointId);
  const { data: fields, isPending, isError, error } = useSchemaFields(
    profileId,
    endpointId,
  );

  const runInference = useRunInference(profileId, endpointId);
  const updateField = useUpdateSchemaField(profileId, endpointId);
  const bulkUpdate = useBulkUpdateSchemaFields(profileId, endpointId);

  const [searchQuery, setSearchQuery] = useState("");
  const [showRerunDialog, setShowRerunDialog] = useState(false);

  // hasUserEdits: user has set alias, type_override, or exclude on any field
  const hasUserEdits =
    fields?.some(
      (f) => f.alias !== null || f.type_override !== null || f.include === false,
    ) ?? false;

  const includedCount = fields?.filter((f) => f.include).length ?? 0;
  const totalCount = fields?.length ?? 0;

  function handleRunInference() {
    if (hasUserEdits) {
      setShowRerunDialog(true);
    } else {
      runInference.mutate();
    }
  }

  function handleConfirmRerun() {
    setShowRerunDialog(false);
    runInference.mutate();
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-6xl">
      {/* Header */}
      <div className="mb-6">
        <button
          type="button"
          className="text-sm text-muted-foreground hover:text-foreground mb-2"
          onClick={() => navigate(`/profiles/${profileId}/endpoints`)}
        >
          ← Back to Endpoints
        </button>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold">Schema Explorer</h1>
            {endpoint && (
              <p className="text-sm text-muted-foreground font-mono mt-0.5">
                {endpoint.name} · {endpoint.path}
              </p>
            )}
          </div>
          {totalCount > 0 && (
            <div className="text-sm text-muted-foreground">
              {includedCount} / {totalCount} fields included
            </div>
          )}
        </div>
      </div>

      {/* Action bar */}
      <div className="flex gap-2 flex-wrap mb-4">
        <Input
          placeholder="Search fields…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="max-w-xs"
        />
        <Button
          variant="outline"
          size="sm"
          disabled={totalCount === 0}
          onClick={() => bulkUpdate.mutate({ include_all: true })}
        >
          Select All
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={totalCount === 0}
          onClick={() => bulkUpdate.mutate({ include_all: false })}
        >
          Deselect All
        </Button>
        <Button
          size="sm"
          disabled={runInference.isPending}
          onClick={handleRunInference}
        >
          {runInference.isPending ? "Running…" : "Run Inference"}
        </Button>
      </div>

      {/* Error banner */}
      {isError && (
        <p className="text-destructive text-sm mb-4">
          {(error as unknown as APIError)?.message ?? "Failed to load schema fields."}
        </p>
      )}
      {runInference.isError && (
        <p className="text-destructive text-sm mb-4">
          {(runInference.error as unknown as APIError)?.message ??
            "Inference failed. Check the endpoint configuration and try again."}
        </p>
      )}

      {/* Loading skeletons */}
      {isPending && (
        <div className="space-y-1 border border-border rounded-lg overflow-hidden">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-12 w-full rounded-none" />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isPending && !isError && totalCount === 0 && (
        <div className="text-center py-16 text-muted-foreground border border-dashed border-border rounded-lg">
          <p className="text-base font-medium mb-1">No schema discovered yet.</p>
          <p className="text-sm mb-4">
            Click &apos;Run Inference&apos; to analyze the API response and discover field types.
          </p>
          <Button onClick={handleRunInference} disabled={runInference.isPending}>
            {runInference.isPending ? "Running…" : "Run Inference"}
          </Button>
        </div>
      )}

      {/* Schema tree */}
      {!isPending && !isError && totalCount > 0 && fields && (
        <SchemaExplorerTree
          fields={fields}
          onUpdate={(fieldId, data) => updateField.mutate({ fieldId, data })}
          isSaving={updateField.isPending}
          searchQuery={searchQuery}
        />
      )}

      {/* Re-run dialog */}
      <RerunInferenceDialog
        isOpen={showRerunDialog}
        hasUserEdits={hasUserEdits}
        isRunning={runInference.isPending}
        onConfirm={handleConfirmRerun}
        onCancel={() => setShowRerunDialog(false)}
      />
    </div>
  );
}