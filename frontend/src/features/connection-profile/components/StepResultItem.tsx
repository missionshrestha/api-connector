// frontend/src/features/connection-profile/components/StepResultItem.tsx
import { CheckCircle2, Lightbulb, Loader2, XCircle } from "lucide-react";
import { STEP_DISPLAY_NAMES, type StepName, type TestStepResult } from "../types";

interface StepResultItemProps {
  stepName: StepName;
  result?: TestStepResult;
  isLoading?: boolean;
  isFuture?: boolean;
}

export function StepResultItem({
  stepName,
  result,
  isLoading = false,
  isFuture = false,
}: StepResultItemProps) {
  const displayName = STEP_DISPLAY_NAMES[stepName];

  // Loading state — test is in progress and this step is "active"
  if (isLoading) {
    return (
      <div className="flex items-start gap-3 py-2">
        <Loader2 className="h-5 w-5 text-muted-foreground animate-spin mt-0.5 shrink-0" />
        <span className="text-sm text-muted-foreground">{displayName}</span>
      </div>
    );
  }

  // Future state — step hasn't run yet
  if (isFuture || result === undefined) {
    return (
      <div className="flex items-start gap-3 py-2 opacity-40">
        <div className="h-5 w-5 rounded-full border-2 border-muted-foreground/30 mt-0.5 shrink-0" />
        <span className="text-sm text-muted-foreground">{displayName}</span>
      </div>
    );
  }

  // Result state — passed or failed
  const suggestedAction = result.detail?.suggested_action as string | undefined;

  if (result.passed) {
    return (
      <div className="flex items-start gap-3 py-2">
        <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
        <div>
          <span className="text-sm font-medium">{displayName}</span>
          <p className="text-xs text-muted-foreground mt-0.5">{result.message}</p>
        </div>
      </div>
    );
  }

  // Failed
  return (
    <div className="flex items-start gap-3 py-2">
      <XCircle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-sm font-semibold text-destructive">{displayName}</span>
        <p className="text-sm text-destructive mt-0.5">{result.message}</p>

        {/* Expandable detail */}
        {Object.keys(result.detail).length > 0 && (
          <details className="mt-1">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
              Show detail
            </summary>
            <div className="mt-1 text-xs text-muted-foreground space-y-0.5">
              {Object.entries(result.detail)
                .filter(([k]) => k !== "suggested_action")
                .map(([key, value]) => (
                  <div key={key} className="font-mono">
                    <span className="text-foreground/60">{key}:</span>{" "}
                    {String(value)}
                  </div>
                ))}
            </div>
          </details>
        )}

        {/* "What to try" callout — only for failed steps with suggested_action */}
        {suggestedAction && (
          <div className="mt-2 flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded p-2">
            <Lightbulb className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 dark:text-amber-300">{suggestedAction}</p>
          </div>
        )}
      </div>
    </div>
  );
}