// frontend/src/features/data-preview/components/CellRenderer.tsx
import { useState } from "react";
import type { InferredType } from "@/shared/types";

const COMPLEX_TRUNCATE_CHARS = 60;

interface CellRendererProps {
  value: unknown;
  effectiveType: InferredType;
}

function formatDatetime(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return String(value);
  try {
    return new Date(value).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return String(value);
  }
}

function formatDate(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return String(value);
  try {
    return new Date(value).toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric",
    });
  } catch {
    return String(value);
  }
}

function ExpandableValue({ raw }: { raw: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const truncated =
    raw.length > COMPLEX_TRUNCATE_CHARS ? raw.slice(0, COMPLEX_TRUNCATE_CHARS) + "…" : raw;

  return (
    <div className="relative">
      <span className="font-mono text-xs text-muted-foreground">{truncated}</span>
      {raw.length > COMPLEX_TRUNCATE_CHARS && (
        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="ml-1 text-xs text-primary underline"
        >
          {isExpanded ? "Collapse" : "Expand"}
        </button>
      )}
      {isExpanded && (
        <div className="absolute z-20 top-full left-0 mt-1 max-w-sm max-h-48 overflow-auto bg-popover border border-border rounded shadow-md p-2">
          <pre className="text-xs font-mono whitespace-pre-wrap break-words">{raw}</pre>
        </div>
      )}
    </div>
  );
}

export function CellRenderer({ value, effectiveType }: CellRendererProps) {
  // ⚠️ CRITICAL: null check MUST come first — before ANY type-based branching.
  // A field with effective_type="integer" that is null must render the null pill,
  // not an attempted number format. String(null) renders as "null" (not the pill).
  if (value === null || value === undefined) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-muted/60 text-muted-foreground font-mono">
        null
      </span>
    );
  }

  // Boolean — green/gray badge
  if (effectiveType === "boolean" || typeof value === "boolean") {
    return (
      <span
        className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
          value
            ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {value ? "True" : "False"}
      </span>
    );
  }

  // Datetime — locale-formatted
  if (effectiveType === "datetime") {
    return <span className="text-sm tabular-nums">{formatDatetime(value)}</span>;
  }

  // Date — locale-formatted
  if (effectiveType === "date") {
    return <span className="text-sm tabular-nums">{formatDate(value)}</span>;
  }

  // Integer / Float — monospace
  if (effectiveType === "integer" || effectiveType === "float") {
    return <span className="font-mono text-sm tabular-nums">{String(value)}</span>;
  }

  // Complex types — expandable
  if (
    effectiveType === "array_of_objects" ||
    effectiveType === "array_of_primitives" ||
    typeof value === "object" ||
    Array.isArray(value)
  ) {
    const raw = JSON.stringify(value, null, 2);
    return <ExpandableValue raw={raw} />;
  }

  // String and all other types — plain text, expandable if very long
  const strVal = String(value);
  if (strVal.length > 120) {
    return <ExpandableValue raw={strVal} />;
  }
  return <span className="text-sm">{strVal}</span>;
}