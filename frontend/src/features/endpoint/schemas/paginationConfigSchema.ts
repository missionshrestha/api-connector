// frontend/src/features/endpoint/schemas/paginationConfigSchema.ts
import { z } from "zod";

// Per-strategy param schemas
const offsetLimitParamsSchema = z.object({
  offset_param: z.string().min(1, "Required"),
  limit_param: z.string().min(1, "Required"),
  page_size: z.number().int().min(1, "Min 1"),
});

const pageSizeParamsSchema = z.object({
  page_param: z.string().min(1, "Required"),
  page_size_param: z.string().min(1, "Required"),
  page_size: z.number().int().min(1),
  total_pages_path: z.string().optional(),
});

const cursorParamsSchema = z.object({
  cursor_request_param: z.string().min(1, "Required"),
  cursor_response_path: z.string().min(1, "Required"),
});

const nextUrlParamsSchema = z.object({
  next_url_response_path: z.string().min(1, "Required"),
});

const strategyParamsSchemas = {
  no_pagination: z.object({}),
  offset_limit: offsetLimitParamsSchema,
  page_size: pageSizeParamsSchema,
  cursor: cursorParamsSchema,
  next_url: nextUrlParamsSchema,
  link_header: z.object({}),
} as const;

export const paginationConfigSchema = z.object({
  strategy: z.enum([
    "no_pagination", "offset_limit", "page_size", "cursor", "next_url", "link_header"
  ]),
  strategy_params: z.record(z.string(), z.unknown()).default({}),
  max_pages: z.number().int().min(1).default(100),
  max_records: z.number().int().min(1).default(10000),
  inter_page_delay_ms: z.number().int().min(0).default(0),
  max_retries: z.number().int().min(0).default(3),
}).superRefine((data, ctx) => {
  const paramsSchema = strategyParamsSchemas[data.strategy];
  if (paramsSchema) {
    const result = paramsSchema.safeParse(data.strategy_params);
    if (!result.success) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Invalid strategy_params for selected strategy",
        path: ["strategy_params"],
      });
    }
  }
});

export type PaginationConfigFormValues = z.infer<typeof paginationConfigSchema>;