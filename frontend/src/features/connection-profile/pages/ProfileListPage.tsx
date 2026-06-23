// frontend/src/features/connection-profile/pages/ProfileListPage.tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import type { APIError } from "@/shared/types";
import { useProfiles, useDeleteProfile } from "../hooks";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { ProfileCard, ProfileCardSkeleton } from "../components/ProfileCard";

export default function ProfileListPage() {
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [deletingProfileId, setDeletingProfileId] = useState<number | null>(null);

  // 300ms debounce: wait for user to stop typing before firing search request
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const { data: profiles, isPending, isError, error } = useProfiles(
    debouncedSearch || undefined
  );
  const deleteProfile = useDeleteProfile();

  const deletingProfile = profiles?.find((p) => p.id === deletingProfileId);

  function handleDeleteConfirm() {
    if (deletingProfileId === null) return;
    deleteProfile.mutate(deletingProfileId, {
      onSuccess: () => setDeletingProfileId(null),
    });
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Connection Profiles</h1>
        <Button asChild>
          <Link to="/profiles/new">New Profile</Link>
        </Button>
      </div>

      <Input
        placeholder="Search profiles…"
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        className="mb-6"
      />

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2">
          <ProfileCardSkeleton />
          <ProfileCardSkeleton />
          <ProfileCardSkeleton />
        </div>
      )}

      {isError && (
        <p className="text-destructive">
          {(error as unknown as APIError)?.message ?? "Failed to load profiles."}
        </p>
      )}

      {!isPending && !isError && profiles?.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          {debouncedSearch ? (
            <p>No profiles match &apos;{debouncedSearch}&apos;.</p>
          ) : (
            <p>
              No profiles yet.{" "}
              <Link to="/profiles/new" className="underline">
                Create your first connection profile.
              </Link>
            </p>
          )}
        </div>
      )}

      {!isPending && !isError && profiles && profiles.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {profiles.map((profile) => (
            <ProfileCard
              key={profile.id}
              profile={profile}
              onDelete={() => setDeletingProfileId(profile.id)}
            />
          ))}
        </div>
      )}

      <DeleteConfirmModal
        profileName={deletingProfile?.name ?? ""}
        isOpen={deletingProfileId !== null}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeletingProfileId(null)}
        isDeleting={deleteProfile.isPending}
      />
    </div>
  );
}