// frontend/src/features/endpoint/components/DataRootPathInput.tsx
import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useDetectDataRoot } from "../hooks";

interface DataRootPathInputProps {
  value: string | null;
  onChange: (v: string | null) => void;
  profileId: number;
  endpointId: number | undefined;
  isEditMode: boolean;
}

type DetectState = "idle" | "detecting" | "success" | "error";

export function DataRootPathInput({
  value,
  onChange,
  profileId,
  endpointId,
  isEditMode,
}: DataRootPathInputProps) {
  const [detectState, setDetectState] = useState<DetectState>("idle");
  const [candidates, setCandidates] = useState<string[]>([]);
  const [detectError, setDetectError] = useState<string | null>(null);

  const detectMutation = useDetectDataRoot(profileId);

  const canAutoDetect = isEditMode && !!endpointId;

  function handleAutoDetect() {
    if (!endpointId) return;
    setDetectState("detecting");
    setDetectError(null);
    detectMutation.mutate(endpointId, {
      onSuccess: (data) => {
        setDetectState("success");
        setCandidates(data.all_candidates);
        if (data.all_candidates.length === 1 && data.top_candidate) {
          onChange(data.top_candidate);
        }
      },
      onError: () => {
        setDetectState("error");
        setDetectError("Auto-detection failed. Enter the path manually.");
      },
    });
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder="data.items"
          className="flex-1"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canAutoDetect || detectState === "detecting"}
          onClick={handleAutoDetect}
          title={
            canAutoDetect
              ? "Makes a live API call to detect the data array path"
              : "Save endpoint first, then auto-detect"
          }
        >
          {detectState === "detecting" ? "Detecting…" : "Auto-Detect"}
        </Button>
      </div>

      {detectState === "success" && candidates.length > 1 && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">
            Multiple arrays found — select one:
          </p>
          <Select
            value={value ?? ""}
            onValueChange={(v) => onChange(v || null)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select a path" />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {detectState === "success" && candidates.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No array of records found in response — enter the path manually.
        </p>
      )}

      {detectState === "error" && detectError && (
        <p className="text-xs text-destructive">{detectError}</p>
      )}

      {!canAutoDetect && (
        <p className="text-xs text-muted-foreground">
          Save the endpoint first to enable auto-detection.
        </p>
      )}
    </div>
  );
}