// frontend/src/features/endpoint/schemas/endpointSchema.ts
import { z } from "zod";

export const endpointSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  path: z.string().min(1, "Path is required").max(2048)
    .refine((v) => v.startsWith("/"), { message: "Path must start with '/'" }),
  method: z.enum(["GET", "POST"]),
  query_params: z.array(
    z.object({ key: z.string().min(1, "Key required"), value: z.string() })
  ),
  path_variables: z.record(z.string(), z.string()),
  request_body: z.record(z.string(), z.unknown()).nullable(),
  endpoint_headers: z.array(
    z.object({ name: z.string().min(1, "Name required"), value: z.string() })
  ),
  data_root_path: z.string().max(500).nullable()
    .refine(
      (v) => !v || /^[\w]+(\.[\w]+)*$/.test(v),
      { message: "Must be dot-notation (e.g. data.items)" }
    ),
  record_count_path: z.string().max(500).nullable()
    .refine(
      (v) => !v || /^[\w]+(\.[\w]+)*$/.test(v),
      { message: "Must be dot-notation" }
    ),
}).superRefine((data, ctx) => {
  if (data.method === "GET" && data.request_body != null) {
    ctx.addIssue({
      code: "custom",
      message: "request_body must be null for GET endpoints",
      path: ["request_body"],
    });
  }
});

export type EndpointFormValues = z.infer<typeof endpointSchema>;