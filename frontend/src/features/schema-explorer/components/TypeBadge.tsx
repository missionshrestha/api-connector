// frontend/src/features/schema-explorer/components/TypeBadge.tsx
import type { InferredType } from "@/shared/types";

interface TypeConfig {
  label: string;
  colorClass: string;
}

const TYPE_CONFIG = {
  null:                 { label: "null",   colorClass: "bg-muted text-muted-foreground" },
  boolean:              { label: "bool",   colorClass: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300" },
  integer:              { label: "int",    colorClass: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
  float:                { label: "float",  colorClass: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
  date:                 { label: "date",   colorClass: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  datetime:             { label: "dt",     colorClass: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  string:               { label: "str",    colorClass: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  mixed:                { label: "mixed",  colorClass: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300" },
  array_of_objects:     { label: "obj[]",  colorClass: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
  array_of_primitives:  { label: "prim[]", colorClass: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
} satisfies Record<InferredType, TypeConfig>;

interface TypeBadgeProps {
  type: InferredType;
}

export function TypeBadge({ type }: TypeBadgeProps) {
  const config = TYPE_CONFIG[type] ?? { label: type, colorClass: "bg-muted text-muted-foreground" };
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-medium ${config.colorClass}`}
    >
      {config.label}
    </span>
  );
}