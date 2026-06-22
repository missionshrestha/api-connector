// frontend/src/features/connection-profile/components/auth-fields/OAuthACAuthFields.tsx
import { Controller } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { OAuthCCAuthFields } from "./OAuthCCAuthFields";
import type { AuthFieldsProps } from "../../types";

export function OAuthACAuthFields(props: AuthFieldsProps) {
  return (
    <div className="space-y-4">
      <OAuthCCAuthFields {...props} />

      <Controller
        name="credentials.authorization_endpoint"
        control={props.control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Authorization Endpoint URL</Label>
            <Input
              {...field}
              value={field.value as string ?? ""}
              type="url"
              placeholder="https://auth.provider.com/authorize"
            />
          </div>
        )}
      />
    </div>
  );
}