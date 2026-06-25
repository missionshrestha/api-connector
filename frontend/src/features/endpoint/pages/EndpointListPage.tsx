// frontend/src/features/endpoint/pages/EndpointListPage.tsx
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import type { APIError } from "@/shared/types";
import { useEndpoints, useDeleteEndpoint } from "../hooks";

export default function EndpointListPage() {
  const { profileId: profileIdStr } = useParams<{ profileId: string }>();
  const profileId = Number(profileIdStr);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const { data: endpoints, isPending, isError, error } = useEndpoints(profileId);
  const deleteEndpoint = useDeleteEndpoint(profileId);

  const deletingEndpoint = endpoints?.find((e) => e.id === deletingId);

  function handleDeleteConfirm() {
    if (deletingId === null) return;
    deleteEndpoint.mutate(deletingId, {
      onSuccess: () => setDeletingId(null),
    });
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link
            to="/profiles"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ← Back to Profiles
          </Link>
          <h1 className="text-2xl font-semibold mt-1">Endpoints</h1>
        </div>
        <Button asChild>
          <Link to={`/profiles/${profileId}/endpoints/new`}>Add Endpoint</Link>
        </Button>
      </div>

      {isPending && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-destructive">
          {(error as unknown as APIError)?.message ?? "Failed to load endpoints."}
        </p>
      )}

      {!isPending && !isError && endpoints?.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <p>No endpoints configured.</p>
          <Link
            to={`/profiles/${profileId}/endpoints/new`}
            className="underline mt-2 inline-block"
          >
            Add your first endpoint.
          </Link>
        </div>
      )}

      {!isPending && !isError && endpoints && endpoints.length > 0 && (
        <div className="space-y-2">
          {endpoints.map((endpoint) => (
            <div
              key={endpoint.id}
              className="flex items-center justify-between p-4 border border-border rounded-lg bg-card"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium">{endpoint.name}</span>
                  <Badge
                    variant={endpoint.method === "GET" ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {endpoint.method}
                  </Badge>
                  {endpoint.has_pagination_config && (
                    <Badge variant="outline" className="text-xs">
                      Paginated
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground font-mono truncate mt-0.5">
                  {endpoint.path}
                </p>
              </div>
              <div className="flex gap-2 ml-3">

                <Button size="sm" variant="ghost" asChild>
                  <Link to={`/profiles/${profileId}/endpoints/${endpoint.id}/schema`}>
                    Schema
                  </Link>
                </Button>

                <Button size="sm" variant="ghost" asChild>
                  <Link to={`/profiles/${profileId}/endpoints/${endpoint.id}/preview`}>
                    Preview
                  </Link>
                </Button>

                <Button size="sm" variant="outline" asChild>
                  <Link
                    to={`/profiles/${profileId}/endpoints/${endpoint.id}/edit`}
                  >
                    Edit
                  </Link>
                </Button>
                
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => setDeletingId(endpoint.id)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <AlertDialog open={deletingId !== null}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete &apos;{deletingEndpoint?.name ?? ""}&apos;?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the endpoint, its schema fields, and
              pagination configuration. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => setDeletingId(null)}
              disabled={deleteEndpoint.isPending}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={deleteEndpoint.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteEndpoint.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}