// frontend/src/features/connection-profile/schemas/profileSchema.ts
import { z } from "zod";

export const profileBaseSchema = z.object({
  name: z.string().min(1, "Required").max(255),
  base_url: z.string().url("Must be a valid URL").max(2048),
  auth_type: z.enum(["none", "api_key", "bearer", "basic", "oauth_cc", "oauth_ac"]),
  ssl_verify: z.boolean(),
  request_timeout: z
    .number({ error: "Must be a number" })
    .int()
    .min(1, "Minimum 1 second")
    .max(120, "Maximum 120 seconds"),
  default_headers: z
    .array(z.object({ name: z.string().min(1, "Header name required"), value: z.string() })),
  // credentials is a passthrough record — validated per-field by auth type schemas
  credentials: z.record(z.string(), z.unknown()),
});

export const profileCreateSchema = profileBaseSchema;
export const profileUpdateSchema = profileBaseSchema.partial();

export type ProfileFormValues = z.infer<typeof profileBaseSchema>;