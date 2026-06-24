// frontend/src/features/schema-explorer/components/AliasInput.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Input } from "@/shared/components/ui/input";

const ALIAS_PATTERN = /^[a-zA-Z0-9_-]*$/;

interface AliasInputProps {
  fieldId: number;
  value: string | null;
  onSave: (fieldId: number, alias: string | null) => void;
  isSaving: boolean;
}

export function AliasInput({ fieldId, value, onSave, isSaving }: AliasInputProps) {
  const [localValue, setLocalValue] = useState(value ?? "");
  const [error, setError] = useState<string | null>(null);
  const [baseline, setBaseline] = useState(value ?? "");

  // Keep in sync with external value updates (e.g. after optimistic update resolves)
  if (value !== null && value !== baseline && !isSaving) {
    setLocalValue(value);
    setBaseline(value);
  }

  function attemptSave() {
    const trimmed = localValue.trim();

    if (trimmed === baseline) return; // No change

    if (trimmed && !ALIAS_PATTERN.test(trimmed)) {
      setError("Alias must use only letters, numbers, underscores, hyphens.");
      return;
    }

    setError(null);
    setBaseline(trimmed);
    onSave(fieldId, trimmed || null);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      attemptSave();
    }
    if (e.key === "Escape") {
      setLocalValue(baseline);
      setError(null);
    }
  }

  return (
    <div className="relative" style={{ maxWidth: 140 }}>
      <Input
        type="text"
        value={localValue}
        maxLength={64}
        placeholder="alias…"
        className={`h-7 text-xs pr-6 font-mono ${error ? "border-destructive" : ""}`}
        onChange={(e) => {
          setLocalValue(e.target.value);
          if (error) setError(null);
        }}
        onBlur={attemptSave}
        onKeyDown={handleKeyDown}
        title={error ?? "Set alias for this field"}
      />
      {isSaving && (
        <Loader2 className="absolute right-1.5 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin text-muted-foreground" />
      )}
      {error && (
        <p className="absolute top-full mt-0.5 text-xs text-destructive whitespace-nowrap z-10 bg-background border border-destructive/30 rounded px-1.5 py-0.5">
          {error}
        </p>
      )}
    </div>
  );
}