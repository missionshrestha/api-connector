// frontend/src/features/connection-profile/components/auth-fields/NoneAuthFields.tsx
import type { FC } from "react";
import type { AuthFieldsProps } from "../../types";

export const NoneAuthFields: FC<AuthFieldsProps> = () => (
  <p className="text-muted-foreground text-sm">
    No credentials required for this auth type.
  </p>
);