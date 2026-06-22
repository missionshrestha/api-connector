// frontend/src/features/connection-profile/components/auth-fields/index.ts
import type { ComponentType } from "react";
import type { AuthType } from "@/shared/types";
import type { AuthFieldsProps } from "../../types";
import { NoneAuthFields } from "./NoneAuthFields";
import { APIKeyAuthFields } from "./APIKeyAuthFields";
import { BearerAuthFields } from "./BearerAuthFields";
import { BasicAuthFields } from "./BasicAuthFields";
import { OAuthCCAuthFields } from "./OAuthCCAuthFields";
import { OAuthACAuthFields } from "./OAuthACAuthFields";

export { NoneAuthFields, APIKeyAuthFields, BearerAuthFields, BasicAuthFields, OAuthCCAuthFields, OAuthACAuthFields };

export const AUTH_FIELDS_COMPONENT_MAP: Record<AuthType, ComponentType<AuthFieldsProps>> = {
  none: NoneAuthFields,
  api_key: APIKeyAuthFields,
  bearer: BearerAuthFields,
  basic: BasicAuthFields,
  oauth_cc: OAuthCCAuthFields,
  oauth_ac: OAuthACAuthFields,
};