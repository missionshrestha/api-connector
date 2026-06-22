// frontend/src/features/connection-profile/schemas/authCredentials.ts
import { z } from "zod";
import type { AuthType } from "@/shared/types";

// ── Create schemas (required fields enforced) ─────────────────────────────────

export const noneCredentialsCreateSchema = z.object({});

export const apiKeyCredentialsCreateSchema = z.object({
  key_name: z.string().min(1, "Required").max(255),
  key_value: z.string().min(1, "Required").max(2048),
  delivery: z.enum(["header", "query"], "Must be 'header' or 'query'"),
  prefix: z.string().max(100).optional(),
});

export const bearerCredentialsCreateSchema = z.object({
  token: z.string().min(1, "Required").max(4096),
  header_name: z.string().max(255).optional(),
});

export const basicCredentialsCreateSchema = z.object({
  username: z.string().min(1, "Required").max(255),
  password: z.string().min(1, "Required").max(2048),
});

export const oauthCCCredentialsCreateSchema = z.object({
  client_id: z.string().min(1, "Required").max(255),
  client_secret: z.string().min(1, "Required").max(2048),
  token_endpoint: z.string().url("Must be a valid URL").max(2048),
  scopes: z.string().max(1024).optional(),
});

export const oauthACCredentialsCreateSchema = oauthCCCredentialsCreateSchema.extend({
  authorization_endpoint: z.string().url("Must be a valid URL").max(2048),
});

// ── Update schemas (all fields optional, empty string = preserve existing) ────

export const noneCredentialsUpdateSchema = z.object({});
export const apiKeyCredentialsUpdateSchema = apiKeyCredentialsCreateSchema.partial().extend({
  key_name: z.string().max(255).optional(),
  key_value: z.string().max(2048).optional(),
  delivery: z.enum(["header", "query"]).optional(),
});
export const bearerCredentialsUpdateSchema = bearerCredentialsCreateSchema.partial();
export const basicCredentialsUpdateSchema = basicCredentialsCreateSchema.partial();
export const oauthCCCredentialsUpdateSchema = oauthCCCredentialsCreateSchema.partial().extend({
  token_endpoint: z.string().url("Must be a valid URL").max(2048).optional(),
});
export const oauthACCredentialsUpdateSchema = oauthACCredentialsCreateSchema.partial().extend({
  token_endpoint: z.string().url("Must be a valid URL").max(2048).optional(),
  authorization_endpoint: z.string().url("Must be a valid URL").max(2048).optional(),
});

// ── Schema maps ───────────────────────────────────────────────────────────────

export const CREDENTIALS_CREATE_SCHEMA_MAP: Record<AuthType, z.ZodTypeAny> = {
  none: noneCredentialsCreateSchema,
  api_key: apiKeyCredentialsCreateSchema,
  bearer: bearerCredentialsCreateSchema,
  basic: basicCredentialsCreateSchema,
  oauth_cc: oauthCCCredentialsCreateSchema,
  oauth_ac: oauthACCredentialsCreateSchema,
};

export const CREDENTIALS_UPDATE_SCHEMA_MAP: Record<AuthType, z.ZodTypeAny> = {
  none: noneCredentialsUpdateSchema,
  api_key: apiKeyCredentialsUpdateSchema,
  bearer: bearerCredentialsUpdateSchema,
  basic: basicCredentialsUpdateSchema,
  oauth_cc: oauthCCCredentialsUpdateSchema,
  oauth_ac: oauthACCredentialsUpdateSchema,
};