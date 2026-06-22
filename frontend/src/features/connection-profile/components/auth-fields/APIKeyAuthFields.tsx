// frontend/src/features/connection-profile/components/auth-fields/APIKeyAuthFields.tsx
import { Controller } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { SecretField } from "../SecretField";
import type { AuthFieldsProps } from "../../types";

export function APIKeyAuthFields({ isEditMode, credentialsSummary, control, errors }: AuthFieldsProps) {
  return (
    <div className="space-y-4">
      <Controller
        name="credentials.key_name"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Key Name</Label>
            <Input {...field} value={field.value as string ?? ""} placeholder="X-API-Key" />
            {errors?.credentials && "key_name" in errors.credentials && (
              <p className="text-destructive text-sm">{String(errors.credentials.key_name?.message)}</p>
            )}
          </div>
        )}
      />

      <Controller
        name="credentials.key_value"
        control={control}
        render={({ field }) => (
          <SecretField
            label="Key Value"
            isSet={credentialsSummary?.key_value?.is_set ?? false}
            isEditMode={isEditMode}
            value={field.value as string ?? ""}
            onChange={field.onChange}
            error={errors?.credentials && "key_value" in errors.credentials
              ? String(errors.credentials.key_value?.message) : undefined}
          />
        )}
      />

      <Controller
        name="credentials.delivery"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Delivery Method</Label>
            <Select value={field.value as string ?? ""} onValueChange={field.onChange}>
              <SelectTrigger>
                <SelectValue placeholder="Select delivery method" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="header">Header</SelectItem>
                <SelectItem value="query">Query Parameter</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}
      />

      <Controller
        name="credentials.prefix"
        control={control}
        render={({ field }) => (
          <div className="space-y-1">
            <Label>Prefix (optional)</Label>
            <Input {...field} value={field.value as string ?? ""} placeholder="e.g. Token" />
          </div>
        )}
      />
    </div>
  );
}