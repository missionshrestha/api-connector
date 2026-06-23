// frontend/src/features/connection-profile/types/index.ts
export * from "./requests";
export * from "./connectionTest";

// Auth field component props — shared interface for all 6 auth type field groups
import type { Control, FieldErrors } from "react-hook-form";
import type { CredentialsSummary } from "@/shared/types";
import type { ProfileFormValues } from "../schemas";

export interface AuthFieldsProps {
  isEditMode: boolean;
  credentialsSummary?: CredentialsSummary | null;
  control: Control<ProfileFormValues>;
  errors?: FieldErrors<ProfileFormValues>;
}