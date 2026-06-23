// frontend/src/features/connection-profile/components/OAuthACStatusBadge.tsx
import { AlertCircle, CheckCircle2, Clock } from "lucide-react";
import type { ComponentType } from "react";
import type { OAuthACStatus } from "../types";

interface OAuthACStatusBadgeProps {
  status: OAuthACStatus;
}

const STATUS_CONFIG: Record<
  OAuthACStatus,
  {
    label: string;
    className: string;
    Icon: ComponentType<{ className?: string }>;
  }
> = {
  authorized: {
    label: "Authorized ✓",
    className:
      "text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800",
    Icon: CheckCircle2,
  },
  authorizing: {
    label: "Waiting for authorization…",
    className:
      "text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800",
    Icon: Clock,
  },
  unauthorized: {
    label: "Not Authorized",
    className: "text-muted-foreground bg-muted border-border",
    Icon: AlertCircle,
  },
  expired: {
    label: "Authorization Expired — Re-authorize",
    className: "text-destructive bg-destructive/10 border-destructive/30",
    Icon: AlertCircle,
  },
};

export function OAuthACStatusBadge({ status }: OAuthACStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const { Icon } = config;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${config.className}`}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  );
}