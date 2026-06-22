// frontend/src/features/connection-profile/components/LastTestIndicator.tsx

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
      <span className="text-muted-foreground text-sm">Never tested</span>
    );
  }

  if (outcome === true) {
    return (
      <span className="text-sm text-green-600 dark:text-green-400">
        ✓ Passed · {formatDate(testedAt)}
      </span>
    );
  }

  return (
    <span className="text-sm text-destructive">
      ✗ Failed{statusCode ? ` · ${statusCode}` : ""} · {formatDate(testedAt)}
    </span>
  );
}