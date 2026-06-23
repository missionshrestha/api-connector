// frontend/src/features/connection-profile/components/ConnectionTestPanel.tsx
import { useEffect, useRef, useState } from "react";
import type { APIError } from "@/shared/types";
import {
  ALL_STEP_NAMES,
  type ConnectionTestResult,
  type StepName,
} from "../types";
import { StepResultItem } from "./StepResultItem";

interface ConnectionTestPanelProps {
  result: ConnectionTestResult | null;
  isRunning: boolean;
  error: unknown | null;
}

export function ConnectionTestPanel({
  result,
  isRunning,
  error,
}: ConnectionTestPanelProps) {
  const [simulatedIndex, setSimulatedIndex] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Progress simulation — advances one step every 800ms while running
    useEffect(() => {
    if (!isRunning) {
        if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
        }
        return;
    }

    // simulatedIndex is already 0 from the previous cleanup
    intervalRef.current = setInterval(() => {
        setSimulatedIndex((prev) =>
        prev < ALL_STEP_NAMES.length - 1 ? prev + 1 : prev,
        );
    }, 800);

    return () => {
        if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
        }
        setSimulatedIndex(0);  // reset here — in cleanup, not effect body
    };
    }, [isRunning]);

  const apiError = error as APIError | null;

  // No result, not running — placeholder
  if (!isRunning && !result && !error) {
    return (
      <div className="py-8 text-center text-muted-foreground text-sm">
        Run a test to see results here.
      </div>
    );
  }

  // Build step result map from actual results
  const resultMap = new Map(result?.steps.map((s) => [s.name, s]) ?? []);
  const completedStepNames = new Set(result?.steps.map((s) => s.name) ?? []);

  // Response sample step (step 6) — for raw response section
  const sampleStep = result?.steps.find((s) => s.name === "response_sample");
  const bodySample = sampleStep?.detail?.body_sample as string | undefined;
  const bodySize = sampleStep?.detail?.body_size_bytes as number | undefined;

  return (
    <div className="space-y-1">
      {/* Error banner */}
      {apiError && (
        <div className="mb-3 p-3 rounded bg-destructive/10 border border-destructive/20">
          <p className="text-sm text-destructive">
            {apiError.message ?? "An error occurred. Please try again."}
          </p>
        </div>
      )}

      {/* Step list */}
      <div className="divide-y divide-border">
        {ALL_STEP_NAMES.map((stepName, index) => {
          if (isRunning) {
            return (
              <StepResultItem
                key={stepName}
                stepName={stepName as StepName}
                isLoading={index <= simulatedIndex}
                isFuture={index > simulatedIndex}
              />
            );
          }

          const stepResult = resultMap.get(stepName);
          return (
            <StepResultItem
              key={stepName}
              stepName={stepName as StepName}
              {...(stepResult !== undefined ? { result: stepResult } : {})}
              isFuture={!completedStepNames.has(stepName)}
            />
          );
        })}
      </div>

      {/* Summary row */}
      {result && !isRunning && (
        <div className="pt-3 border-t flex items-center justify-between text-sm">
          <span
            className={
              result.overall_passed
                ? "font-semibold text-green-600 dark:text-green-400"
                : "font-semibold text-destructive"
            }
          >
            {result.overall_passed ? "✓ Test passed" : "✗ Test failed"}
          </span>
          <span className="text-muted-foreground">
            Completed in {result.duration_ms}ms
          </span>
        </div>
      )}

      {/* Raw Response — only when step 6 completed */}
      {bodySample !== undefined && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
            Raw Response ({bodySize ?? 0} bytes)
          </summary>
          <div className="mt-2 relative">
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(bodySample)}
              className="absolute top-2 right-2 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded border border-border bg-background"
            >
              Copy
            </button>
            <pre className="font-mono text-xs overflow-x-auto max-h-64 p-3 rounded bg-muted text-foreground whitespace-pre-wrap break-words">
              {bodySample}
            </pre>
          </div>
        </details>
      )}
    </div>
  );
}