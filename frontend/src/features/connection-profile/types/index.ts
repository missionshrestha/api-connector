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
  // New in Phase 4: oauth_ac_authorized from profile read response
  oauthAcAuthorized?: boolean | null;
  // New in Phase 4: profile ID — needed to enable the Authorize button
  profileId?: number | undefined;
}