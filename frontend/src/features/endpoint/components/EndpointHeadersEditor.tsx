// frontend/src/features/endpoint/components/EndpointHeadersEditor.tsx
import { Trash2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

interface HeaderRow {
  name: string;
  value: string;
}

interface EndpointHeadersEditorProps {
  value: HeaderRow[];
  onChange: (headers: HeaderRow[]) => void;
}

export function EndpointHeadersEditor({ value, onChange }: EndpointHeadersEditorProps) {
  return (
    <div className="space-y-2">
      {value.map((row, index) => (
        <div key={index} className="flex gap-2 items-center">
          <Input
            placeholder="Header Name"
            value={row.name}
            onChange={(e) =>
              onChange(value.map((r, i) => i === index ? { ...r, name: e.target.value } : r))
            }
            className="flex-1"
          />
          <Input
            placeholder="Value"
            value={row.value}
            onChange={(e) =>
              onChange(value.map((r, i) => i === index ? { ...r, value: e.target.value } : r))
            }
            className="flex-1"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {value.length === 0 && (
        <p className="text-muted-foreground text-sm">No custom headers.</p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...value, { name: "", value: "" }])}
      >
        Add Header
      </Button>
    </div>
  );
}