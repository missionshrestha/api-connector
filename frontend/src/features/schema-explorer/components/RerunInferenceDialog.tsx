// frontend/src/features/schema-explorer/components/RerunInferenceDialog.tsx
import { Loader2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";

interface RerunInferenceDialogProps {
  isOpen: boolean;
  hasUserEdits: boolean;
  isRunning: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RerunInferenceDialog({
  isOpen,
  hasUserEdits,
  isRunning,
  onConfirm,
  onCancel,
}: RerunInferenceDialogProps) {
  // If no user edits, caller should bypass the dialog entirely.
  // This component also handles the open=true/hasUserEdits=false edge case gracefully.
  if (!hasUserEdits) return null;

  return (
    <AlertDialog open={isOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Re-run Schema Inference?</AlertDialogTitle>
          <AlertDialogDescription>
            Re-running will update inferred types and null percentages based on
            the latest API response.{" "}
            <strong>
              Your aliases, include selections, and type overrides will be
              preserved.
            </strong>{" "}
            Fields no longer present in the response will be marked as stale
            rather than deleted.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel} disabled={isRunning}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} disabled={isRunning}>
            {isRunning ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Running…
              </>
            ) : (
              "Re-run Inference"
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}