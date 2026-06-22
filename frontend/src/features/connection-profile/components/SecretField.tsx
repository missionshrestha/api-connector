// frontend/src/features/connection-profile/components/SecretField.tsx
import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";

// SECURITY: The masked display (••••••••) is a hardcoded constant string.
// It is NEVER derived from the actual credential value. The real value
// is never rendered into the DOM. ASVS 3.5.2.
const MASK_DISPLAY = "••••••••";

interface SecretFieldProps {
  label: string;
  isSet: boolean;           // from credentials_summary[fieldName].is_set
  isEditMode: boolean;      // false = create form, true = edit form
  value: string;
  onChange: (value: string) => void;
  error?: string | undefined;
  placeholder?: string;
}

export function SecretField({
  label,
  isSet,
  isEditMode,
  value,
  onChange,
  error,
  placeholder,
}: SecretFieldProps) {
  const [isChanging, setIsChanging] = useState(false);

  const handleKeepExisting = () => {
    setIsChanging(false);
    onChange(""); // Empty string signals "preserve existing" to the update serializer
  };

  // ── Create mode: always show password input ───────────────────────────────
  if (!isEditMode) {
    return (
      <div className="space-y-1">
        <Label>{label}</Label>
        <Input
          type="password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="new-password"
        />
        {error && <p className="text-destructive text-sm">{error}</p>}
      </div>
    );
  }

  // ── Edit mode, existing secret, not yet changing ───────────────────────────
  if (isEditMode && isSet && !isChanging) {
    return (
      <div className="space-y-1">
        <Label>{label}</Label>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground font-mono text-sm tracking-widest">
            {MASK_DISPLAY}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setIsChanging(true)}
          >
            Change
          </Button>
        </div>
        {error && <p className="text-destructive text-sm">{error}</p>}
      </div>
    );
  }

  // ── Edit mode, changing (or no existing secret) ────────────────────────────
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <div className="flex gap-2">
        <Input
          type="password"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoFocus={isChanging}
          autoComplete="new-password"
          className="flex-1"
        />
        {isSet && isChanging && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleKeepExisting}
          >
            Keep Existing
          </Button>
        )}
      </div>
      {error && <p className="text-destructive text-sm">{error}</p>}
    </div>
  );
}