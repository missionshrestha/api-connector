// frontend/src/features/connection-profile/components/AuthTypeBadge.tsx
import { KeyRound, Lock, ShieldCheck, ShieldOff, Unlock } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { AuthType } from "@/shared/types";

const AUTH_TYPE_CONFIG: Record<AuthType, { label: string; icon: LucideIcon }> = {
  none: { label: "No Auth", icon: ShieldOff },
  api_key: { label: "API Key", icon: KeyRound },
  bearer: { label: "Bearer Token", icon: Unlock },
  basic: { label: "Basic Auth", icon: Lock },
  oauth_cc: { label: "OAuth CC", icon: ShieldCheck },
  oauth_ac: { label: "OAuth AC", icon: ShieldCheck },
};

interface AuthTypeBadgeProps {
  authType: AuthType;
}

export function AuthTypeBadge({ authType }: AuthTypeBadgeProps) {
  const config = AUTH_TYPE_CONFIG[authType] ?? { label: authType, icon: ShieldOff };
  const Icon = config.icon;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-xs font-medium text-muted-foreground">
      <Icon className="size-3 shrink-0" />
      {config.label}
    </span>
  );
}
