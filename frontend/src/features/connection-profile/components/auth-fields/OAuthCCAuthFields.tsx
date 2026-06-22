// frontend/src/features/connection-profile/components/auth-fields/OAuthCCAuthFields.tsx
import { Controller } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { SecretField } from "../SecretField";
import type { AuthFieldsProps } from "../../types";

export function OAuthCCAuthFields({ isEditMode, credentialsSummary, control }: AuthFieldsProps) {
  return (
    <div className="space-y-4">
      <Controller
        name="credentials.client_id"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Client ID</Label>
            <Input {...field} value={field.value as string ?? ""} placeholder="your-client-id" />
          </div>
        )}
      />

      <Controller
        name="credentials.client_secret"
        control={control}
        render={({ field }) => (
          <SecretField
            label="Client Secret"
            isSet={credentialsSummary?.client_secret?.is_set ?? false}
            isEditMode={isEditMode}
            value={field.value as string ?? ""}
            onChange={field.onChange}
          />
        )}
      />

      <Controller
        name="credentials.token_endpoint"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Token Endpoint URL</Label>
            <Input
              {...field}
              value={field.value as string ?? ""}
              type="url"
              placeholder="https://auth.provider.com/token"
            />
          </div>
        )}
      />

      <Controller
        name="credentials.scopes"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Scopes (optional)</Label>
            <Input {...field} value={field.value as string ?? ""} placeholder="read write" />
          </div>
        )}
      />
    </div>
  );
}