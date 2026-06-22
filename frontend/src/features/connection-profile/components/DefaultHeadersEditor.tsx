// frontend/src/features/connection-profile/components/DefaultHeadersEditor.tsx
import { Trash2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

interface HeaderRow {
  name: string;
  value: string;
}

interface DefaultHeadersEditorProps {
  value: HeaderRow[];
  onChange: (headers: HeaderRow[]) => void;
}

export function DefaultHeadersEditor({ value, onChange }: DefaultHeadersEditorProps) {
  function handleAdd() {
    onChange([...value, { name: "", value: "" }]);
  }

  function handleNameChange(index: number, newName: string) {
    const updated = value.map((row, i) =>
      i === index ? { ...row, name: newName } : row
    );
    onChange(updated);
  }

  function handleValueChange(index: number, newValue: string) {
    const updated = value.map((row, i) =>
      i === index ? { ...row, value: newValue } : row
    );
    onChange(updated);
  }

  function handleRemove(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <p className="text-muted-foreground text-sm">No default headers configured.</p>
      )}

      {value.map((row, index) => (
        <div key={index} className="flex gap-2 items-center">
          <Input
            placeholder="Header Name"
            value={row.name}
            onChange={(e) => handleNameChange(index, e.target.value)}
            className="flex-1"
          />
          <Input
            placeholder="Header Value"
            value={row.value}
            onChange={(e) => handleValueChange(index, e.target.value)}
            className="flex-1"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => handleRemove(index)}
            aria-label="Remove header"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}

      <Button type="button" variant="outline" size="sm" onClick={handleAdd}>
        Add Header
      </Button>
    </div>
  );
}