// frontend/src/features/endpoint/components/PathVariableEditor.tsx
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";

interface PathVariableEditorProps {
  pathVariables: Record<string, string>;
  onChange: (vars: Record<string, string>) => void;
  detectedNames: string[];
}

export function PathVariableEditor({
  pathVariables,
  onChange,
  detectedNames,
}: PathVariableEditorProps) {
  if (detectedNames.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No path variables detected. Use {"{variable}"} syntax in the path.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {detectedNames.map((name) => (
        <div key={name} className="flex gap-2 items-center">
          <Label className="w-32 shrink-0 font-mono text-sm text-muted-foreground">
            {`{${name}}`}
          </Label>
          <Input
            placeholder={`Value for ${name}`}
            value={pathVariables[name] ?? ""}
            onChange={(e) =>
              onChange({ ...pathVariables, [name]: e.target.value })
            }
          />
        </div>
      ))}
    </div>
  );
}