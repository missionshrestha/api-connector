// frontend/src/features/endpoint/components/PaginationStrategySelector.tsx
import { Label } from "@/shared/components/ui/label";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { PaginationStrategy } from "@/shared/types";
import type { PaginationConfigFormValues } from "../schemas";

interface PaginationStrategySelectorProps {
  value: PaginationConfigFormValues;
  onChange: (v: PaginationConfigFormValues) => void;
}

const STRATEGY_LABELS: Record<PaginationStrategy, string> = {
  no_pagination: "No Pagination",
  offset_limit: "Offset / Limit",
  page_size: "Page Number + Size",
  cursor: "Cursor-Based",
  next_url: "Next URL in Response",
  link_header: "Link Header (RFC 5988)",
};

function StrategyParamsFields({
  strategy,
  params,
  onParamsChange,
}: {
  strategy: PaginationStrategy;
  params: Record<string, unknown>;
  onParamsChange: (p: Record<string, unknown>) => void;
}) {
  const set = (key: string, val: unknown) => onParamsChange({ ...params, [key]: val });

  if (strategy === "no_pagination") {
    return (
      <p className="text-muted-foreground text-sm bg-muted/40 rounded p-3">
        No pagination configuration required — all records returned in one request.
      </p>
    );
  }

  if (strategy === "offset_limit") {
    return (
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-1">
          <Label>Offset Param Name</Label>
          <Input
            placeholder="offset"
            value={(params.offset_param as string) ?? ""}
            onChange={(e) => set("offset_param", e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label>Limit Param Name</Label>
          <Input
            placeholder="limit"
            value={(params.limit_param as string) ?? ""}
            onChange={(e) => set("limit_param", e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label>Page Size</Label>
          <Input
            type="number"
            placeholder="20"
            value={(params.page_size as number) ?? ""}
            onChange={(e) => set("page_size", e.target.valueAsNumber)}
          />
        </div>
      </div>
    );
  }

  if (strategy === "page_size") {
    return (
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Page Param Name</Label>
          <Input
            placeholder="page"
            value={(params.page_param as string) ?? ""}
            onChange={(e) => set("page_param", e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label>Page Size Param Name</Label>
          <Input
            placeholder="per_page"
            value={(params.page_size_param as string) ?? ""}
            onChange={(e) => set("page_size_param", e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label>Page Size</Label>
          <Input
            type="number"
            placeholder="20"
            value={(params.page_size as number) ?? ""}
            onChange={(e) => set("page_size", e.target.valueAsNumber)}
          />
        </div>
        <div className="space-y-1">
          <Label>Total Pages Path (optional)</Label>
          <Input
            placeholder="meta.total_pages"
            value={(params.total_pages_path as string) ?? ""}
            onChange={(e) => set("total_pages_path", e.target.value || undefined)}
          />
        </div>
      </div>
    );
  }

  if (strategy === "cursor") {
    return (
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Cursor Request Param</Label>
          <Input
            placeholder="after"
            value={(params.cursor_request_param as string) ?? ""}
            onChange={(e) => set("cursor_request_param", e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label>Cursor Response Path</Label>
          <Input
            placeholder="meta.next_cursor"
            value={(params.cursor_response_path as string) ?? ""}
            onChange={(e) => set("cursor_response_path", e.target.value)}
          />
        </div>
      </div>
    );
  }

  if (strategy === "next_url") {
    return (
      <div className="space-y-1">
        <Label>Next URL Response Path</Label>
        <Input
          placeholder="links.next"
          value={(params.next_url_response_path as string) ?? ""}
          onChange={(e) => set("next_url_response_path", e.target.value)}
        />
      </div>
    );
  }

  if (strategy === "link_header") {
    return (
      <p className="text-muted-foreground text-sm bg-muted/40 rounded p-3">
        No params required — reads the RFC 5988 Link header automatically.
      </p>
    );
  }

  return null;
}

export function PaginationStrategySelector({
  value,
  onChange,
}: PaginationStrategySelectorProps) {
  function handleStrategyChange(newStrategy: string) {
    // Clear strategy_params when switching — preserve safety fields
    onChange({
      ...value,
      strategy: newStrategy as PaginationStrategy,
      strategy_params: {},
    });
  }

  function handleParamsChange(newParams: Record<string, unknown>) {
    onChange({ ...value, strategy_params: newParams });
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Label>Pagination Strategy</Label>
        <Select value={value.strategy} onValueChange={handleStrategyChange}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.entries(STRATEGY_LABELS) as [PaginationStrategy, string][]).map(
              ([key, label]) => (
                <SelectItem key={key} value={key}>
                  {label}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>
      </div>

      <StrategyParamsFields
        strategy={value.strategy}
        params={value.strategy_params as Record<string, unknown>}
        onParamsChange={handleParamsChange}
      />

      {/* Safety fields — always shown, preserved on strategy switch */}
      <div className="border-t pt-4 grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Max Pages</Label>
          <Input
            type="number"
            value={value.max_pages}
            onChange={(e) => onChange({ ...value, max_pages: e.target.valueAsNumber })}
          />
        </div>
        <div className="space-y-1">
          <Label>Max Records</Label>
          <Input
            type="number"
            value={value.max_records}
            onChange={(e) => onChange({ ...value, max_records: e.target.valueAsNumber })}
          />
        </div>
        <div className="space-y-1">
          <Label>Inter-Page Delay (ms)</Label>
          <Input
            type="number"
            value={value.inter_page_delay_ms}
            onChange={(e) =>
              onChange({ ...value, inter_page_delay_ms: e.target.valueAsNumber })
            }
          />
        </div>
        <div className="space-y-1">
          <Label>Max Retries</Label>
          <Input
            type="number"
            value={value.max_retries}
            onChange={(e) => onChange({ ...value, max_retries: e.target.valueAsNumber })}
          />
        </div>
      </div>
    </div>
  );
}