// frontend/src/features/connection-profile/components/LastTestIndicator.tsx
import { CheckCircle2, MinusCircle, XCircle } from "lucide-react";

interface LastTestIndicatorProps {
  outcome: boolean | null;
  testedAt: string | null;
  statusCode: number | null;
}

function formatDate(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return "Unknown date";
  }
}

export function LastTestIndicator({ outcome, testedAt, statusCode }: LastTestIndicatorProps) {
  if (outcome === null || testedAt === null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
        <MinusCircle className="size-3.5 shrink-0" />
        Never tested
      </span>
    );
  }

  if (outcome === true) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 className="size-3.5 shrink-0" />
        <span className="text-foreground/80">Passed · {formatDate(testedAt)}</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-destructive">
      <XCircle className="size-3.5 shrink-0" />
      <span className="text-foreground/80">
        Failed{statusCode ? ` · ${statusCode}` : ""} · {formatDate(testedAt)}
      </span>
    </span>
  );
}
