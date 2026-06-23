// frontend/src/features/connection-profile/components/auth-fields/OAuthACAuthFields.tsx
import { Controller } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Button } from "@/shared/components/ui/button";
import { OAuthCCAuthFields } from "./OAuthCCAuthFields";
import { OAuthACStatusBadge } from "../OAuthACStatusBadge";
import { useOAuthAuthorize } from "../../hooks/useOAuthAuthorize";
import type { AuthFieldsProps } from "../../types";

export function OAuthACAuthFields({
  isEditMode,
  credentialsSummary,
  control,
  errors,
  oauthAcAuthorized,
  profileId,
}: AuthFieldsProps) {
  // Derive initial status from the profile's authorization state in DB
  const derivedInitialStatus =
    oauthAcAuthorized === true ? "authorized" : "unauthorized";

  const { status, isAuthorizing, error, authorize } = useOAuthAuthorize({
    profileId,
    initialStatus: derivedInitialStatus,
  });

  // Determine whether credential fields are set (required for authorization)
  const requiredFieldsSet =
    credentialsSummary?.client_id?.is_set &&
    credentialsSummary?.client_secret?.is_set &&
    credentialsSummary?.authorization_endpoint?.is_set &&
    credentialsSummary?.token_endpoint?.is_set;

  // Authorize button is only enabled after profile is saved and credentials are stored
  const canAuthorize = isEditMode && !!profileId && !!requiredFieldsSet;

  return (
    <div className="space-y-4">
      {/* OAuth CC fields shared with CC: client_id, client_secret, token_endpoint, scopes */}
      <OAuthCCAuthFields
        isEditMode={isEditMode}
        credentialsSummary={credentialsSummary ?? null}
        control={control}
        errors={errors ?? {}}
      />

      {/* Authorization Endpoint (AC-specific) */}
      <Controller
        name="credentials.authorization_endpoint"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Authorization Endpoint URL</Label>
            <Input
              {...field}
              value={(field.value as string) ?? ""}
              type="url"
              placeholder="https://auth.provider.com/authorize"
            />
          </div>
        )}
      />

      {/* Authorization flow section */}
      <div className="rounded-md border border-border p-4 space-y-3 bg-muted/30">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-medium">Browser Authorization</p>
            <p className="text-xs text-muted-foreground">
              {canAuthorize
                ? "Click Authorize to open the provider consent window."
                : isEditMode
                  ? "Save profile credentials above before authorizing."
                  : "Save the profile first, then return to authorize."}
            </p>
          </div>
          <OAuthACStatusBadge status={status} />
        </div>

        <Button
          type="button"
          variant={status === "authorized" ? "outline" : "default"}
          size="sm"
          disabled={!canAuthorize || isAuthorizing}
          onClick={authorize}
        >
          {isAuthorizing
            ? "Waiting for browser…"
            : status === "authorized"
              ? "Re-Authorize"
              : "Authorize"}
        </Button>

        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}
      </div>
    </div>
  );
}