// frontend/src/features/connection-profile/components/ProfileCard.tsx
import { useNavigate } from "react-router-dom";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import type { ConnectionProfile } from "@/shared/types";
import { AuthTypeBadge } from "./AuthTypeBadge";
import { LastTestIndicator } from "./LastTestIndicator";

interface ProfileCardProps {
  profile: ConnectionProfile;
  onDelete: () => void;
  onReTest: () => void;
}

export function ProfileCard({ profile, onDelete, onReTest }: ProfileCardProps) {
  const navigate = useNavigate();

  const handleReTest = () => {
    // TODO Phase 3: implement connection test
    onReTest();
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{profile.name}</CardTitle>
          <AuthTypeBadge authType={profile.auth_type} />
        </div>
        <p className="text-xs text-muted-foreground font-mono truncate">
          {profile.base_url}
        </p>
      </CardHeader>
      <CardContent className="pb-3">
        <LastTestIndicator
          outcome={profile.last_test_outcome}
          testedAt={profile.last_test_at}
          statusCode={profile.last_test_status_code}
        />
        <div className="flex gap-2 mt-3">
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/profiles/${profile.id}/edit`)}
          >
            Edit
          </Button>

          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" variant="outline" disabled onClick={handleReTest}>
                  Re-Test
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              Test connection — available after Phase 3
            </TooltipContent>
          </Tooltip>

          <Button
            size="sm"
            variant="destructive"
            onClick={onDelete}
          >
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
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
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-8 w-16" />
        </div>
      </CardContent>
    </Card>
  );
}