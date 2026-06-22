// frontend/src/features/connection-profile/components/auth-fields/BearerAuthFields.tsx
import { Controller } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { SecretField } from "../SecretField";
import type { AuthFieldsProps } from "../../types";

export function BearerAuthFields({ isEditMode, credentialsSummary, control }: AuthFieldsProps) {
  return (
    <div className="space-y-4">
      <Controller
        name="credentials.token"
        control={control}
        render={({ field }) => (
          <SecretField
            label="Bearer Token"
            isSet={credentialsSummary?.token?.is_set ?? false}
            isEditMode={isEditMode}
            value={field.value as string ?? ""}
            onChange={field.onChange}
          />
        )}
      />

      <Controller
        name="credentials.header_name"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Header Name (optional, default: Authorization)</Label>
            <Input {...field} value={field.value as string ?? ""} placeholder="Authorization" />
          </div>
        )}
      />
    </div>
  );
}