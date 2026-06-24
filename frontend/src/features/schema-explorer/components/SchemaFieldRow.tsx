// frontend/src/features/schema-explorer/components/SchemaFieldRow.tsx
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import type { ArrayHandling, InferredType, SchemaField } from "@/shared/types";
import { AliasInput } from "./AliasInput";
import { NullPercentageBar } from "./NullPercentageBar";
import { TypeBadge } from "./TypeBadge";
import type { UpdateSchemaFieldRequest } from "../api/schemaApi";

const INFERRED_TYPE_OPTIONS: InferredType[] = [
  "null", "boolean", "integer", "float", "date", "datetime",
  "string", "mixed", "array_of_objects", "array_of_primitives",
];

interface SchemaFieldRowProps {
  field: SchemaField;
  depth: number;
  onUpdate: (fieldId: number, data: UpdateSchemaFieldRequest) => void;
  isSaving: boolean;
  /** If the field has children in the tree, pass a toggle callback */
  isExpandable?: boolean;
  isExpanded?: boolean;
  onToggleExpand?: () => void;
}

function truncateSampleValue(v: unknown, maxChars = 40): string {
  if (v === null || v === undefined) return "";
  const str = typeof v === "string" ? v : JSON.stringify(v);
  return str.length > maxChars ? str.slice(0, maxChars) + "…" : str;
}

export function SchemaFieldRow({
  field,
  depth,
  onUpdate,
  isSaving,
  isExpandable = false,
  isExpanded = false,
  onToggleExpand,
}: SchemaFieldRowProps) {
  const effectiveType = field.type_override ?? field.inferred_type;
  const showArrayHandling =
    effectiveType === "array_of_objects" || field.inferred_type === "array_of_objects";

  const segments = field.key_path.split(".");
  const lastSegment = segments[segments.length - 1] || field.key_path;
  const sample = truncateSampleValue(field.sample_value);

  return (
    <div
      data-schema-field-row
      className={`flex items-center gap-2 h-12 px-2 border-b border-border/50 hover:bg-muted/20 transition-colors ${
        field.stale ? "opacity-50" : ""
      }`}
      style={{ paddingLeft: `${8 + depth * 16}px` }}
    >
      {/* Expand/collapse toggle */}
      <button
        type="button"
        className={`w-4 h-4 shrink-0 flex items-center justify-center text-muted-foreground ${
          isExpandable ? "cursor-pointer hover:text-foreground" : "invisible"
        }`}
        onClick={isExpandable ? onToggleExpand : undefined}
        aria-label={isExpanded ? "Collapse" : "Expand"}
      >
        {isExpandable && (isExpanded ? "▾" : "▸")}
      </button>

      {/* Include checkbox */}
      <Checkbox
        checked={field.include}
        onCheckedChange={(checked) =>
          onUpdate(field.id, { include: !!checked })
        }
        className="shrink-0"
        aria-label={`Include ${field.key_path}`}
      />

      {/* Field path */}
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-sm font-mono truncate min-w-0 flex-1 cursor-default">
            {lastSegment}
          </span>
        </TooltipTrigger>
        <TooltipContent>{field.key_path}</TooltipContent>
      </Tooltip>

      {/* Stale indicator */}
      {field.stale && (
        <Tooltip>
          <TooltipTrigger>
            <span className="text-amber-500 text-xs shrink-0">⚠</span>
          </TooltipTrigger>
          <TooltipContent>Not seen in latest sample</TooltipContent>
        </Tooltip>
      )}

      {/* Type badge */}
      <TypeBadge type={effectiveType} />

      {/* Sample value */}
      {sample && (
        <span className="text-xs text-muted-foreground font-mono truncate max-w-[80px] shrink-0">
          {sample}
        </span>
      )}
      {field.sample_value === null && (
        <span className="text-xs text-muted-foreground italic shrink-0">null</span>
      )}

      {/* Null % bar */}
      <NullPercentageBar nullPercentage={field.null_percentage} />

      {/* Alias input */}
      <AliasInput
        fieldId={field.id}
        value={field.alias}
        onSave={(id, alias) => onUpdate(id, { alias })}
        isSaving={isSaving}
      />

      {/* Type override */}
      <Select
        value={field.type_override ?? ""}
        onValueChange={(v) =>
          onUpdate(field.id, { type_override: v || null })
        }
      >
        <SelectTrigger className="h-7 text-xs w-24 shrink-0">
          <SelectValue placeholder="Override…" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="">No override</SelectItem>
          {INFERRED_TYPE_OPTIONS.map((t) => (
            <SelectItem key={t} value={t}>
              {t}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Array handling — only for array_of_objects */}
      {showArrayHandling && (
        <Select
          value={field.array_handling ?? ""}
          onValueChange={(v) =>
            onUpdate(field.id, { array_handling: (v as ArrayHandling) || null })
          }
        >
          <SelectTrigger className="h-7 text-xs w-20 shrink-0">
            <SelectValue placeholder="Array…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">Default</SelectItem>
            <SelectItem value="expand">Expand</SelectItem>
            <SelectItem value="retain">Retain</SelectItem>
          </SelectContent>
        </Select>
      )}
    </div>
  );
}