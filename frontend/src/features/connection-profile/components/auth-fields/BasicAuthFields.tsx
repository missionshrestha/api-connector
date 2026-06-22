// frontend/src/features/connection-profile/components/auth-fields/BasicAuthFields.tsx
import { Controller } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { SecretField } from "../SecretField";
import type { AuthFieldsProps } from "../../types";

export function BasicAuthFields({ isEditMode, credentialsSummary, control }: AuthFieldsProps) {
  return (
    <div className="space-y-4">
      <Controller
        name="credentials.username"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Username</Label>
            <Input {...field} value={field.value as string ?? ""} placeholder="username" />
          </div>
        )}
      />

      <Controller
        name="credentials.password"
        control={control}
        render={({ field }) => (
          <SecretField
            label="Password"
            isSet={credentialsSummary?.password?.is_set ?? false}
            isEditMode={isEditMode}
            value={field.value as string ?? ""}
            onChange={field.onChange}
          />
        )}
      />
    </div>
  );
}