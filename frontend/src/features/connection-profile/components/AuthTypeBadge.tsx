// frontend/src/features/connection-profile/components/AuthTypeBadge.tsx
import { Badge } from "@/shared/components/ui/badge";
import type { AuthType } from "@/shared/types";

type BadgeVariant = "default" | "secondary" | "outline" | "destructive";

const AUTH_TYPE_CONFIG: Record<AuthType, { label: string; variant: BadgeVariant }> = {
  none: { label: "No Auth", variant: "secondary" },
  api_key: { label: "API Key", variant: "default" },
  bearer: { label: "Bearer Token", variant: "default" },
  basic: { label: "Basic Auth", variant: "outline" },
  oauth_cc: { label: "OAuth CC", variant: "default" },
  oauth_ac: { label: "OAuth AC", variant: "default" },
};

interface AuthTypeBadgeProps {
  authType: AuthType;
}

export function AuthTypeBadge({ authType }: AuthTypeBadgeProps) {
  const config = AUTH_TYPE_CONFIG[authType] ?? { label: authType, variant: "secondary" };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}