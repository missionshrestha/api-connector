// frontend/src/features/data-preview/components/ColumnHeaderTooltip.tsx
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import { TypeBadge } from "@/features/schema-explorer/components/TypeBadge";
import type { PreviewColumnMeta } from "../types";

interface ColumnHeaderTooltipProps {
  column: PreviewColumnMeta;
}

function formatSampleValue(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "string") return v.slice(0, 60);
  return JSON.stringify(v).slice(0, 60);
}

export function ColumnHeaderTooltip({ column }: ColumnHeaderTooltipProps) {
  const nullPct = Math.round(column.null_percentage * 100);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="w-full text-left font-medium text-sm truncate hover:text-primary"
        >
          {column.name}
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs space-y-1.5 p-3">
        <div className="flex items-center gap-2">
          <TypeBadge type={column.effective_type} />
          <span className="text-xs text-muted-foreground font-mono">
            {column.key_path}
          </span>
        </div>
        <div className="text-xs text-muted-foreground">
          {nullPct}% null
          {column.sample_value !== null && column.sample_value !== undefined && (
            <span className="ml-2 font-mono text-foreground">
              e.g. {formatSampleValue(column.sample_value)}
            </span>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}