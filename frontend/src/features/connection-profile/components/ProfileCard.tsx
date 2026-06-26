// frontend/src/features/connection-profile/components/ProfileCard.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, PlugZap, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import type { ConnectionProfile } from "@/shared/types";
import { AuthTypeBadge } from "./AuthTypeBadge";
import { ConnectionTestModal } from "./ConnectionTestModal";
import { LastTestIndicator } from "./LastTestIndicator";

interface ProfileCardProps {
  profile: ConnectionProfile;
  onDelete: () => void;
}

export function ProfileCard({ profile, onDelete }: ProfileCardProps) {
  const navigate = useNavigate();
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  return (
    <>
      <Card className="transition-shadow hover:shadow-md">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base">{profile.name}</CardTitle>
            <AuthTypeBadge authType={profile.auth_type} />
          </div>
          <p className="truncate font-mono text-xs text-muted-foreground">
            {profile.base_url}
          </p>
        </CardHeader>
        <CardContent>
          <LastTestIndicator
            outcome={profile.last_test_outcome}
            testedAt={profile.last_test_at}
            statusCode={profile.last_test_status_code}
          />
          <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
            <Button
              size="sm"
              onClick={() => navigate(`/profiles/${profile.id}/endpoints`)}
            >
              Endpoints
              <ArrowRight className="size-3.5" />
            </Button>

            <Button
              size="sm"
              variant="outline"
              onClick={() => setIsTestModalOpen(true)}
            >
              <PlugZap className="size-3.5" />
              Test
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={() => navigate(`/profiles/${profile.id}/edit`)}
            >
              <Pencil className="size-3.5" />
              Edit
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={onDelete}
              aria-label={`Delete ${profile.name}`}
              className="ml-auto text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <ConnectionTestModal
        profileId={profile.id}
        profileName={profile.name}
        isOpen={isTestModalOpen}
        onClose={() => setIsTestModalOpen(false)}
      />
    </>
  );
}

export function ProfileCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-3 w-64 mt-1" />
      </CardHeader>
      <CardContent className="pb-3">
        <Skeleton className="h-4 w-32" />
        <div className="flex gap-2 mt-3">
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-8 w-28" />
          <Skeleton className="h-8 w-16" />
        </div>
      </CardContent>
    </Card>
  );
}