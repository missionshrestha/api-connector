// frontend/src/features/data-preview/components/ExportButtons.tsx
import { Button } from "@/shared/components/ui/button";
import { exportToCsv, exportToJson } from "../api/exportUtils";
import type { PreviewResult } from "../types";

interface ExportButtonsProps {
  result: PreviewResult;
  endpointName: string;
}

export function ExportButtons({ result, endpointName }: ExportButtonsProps) {
  return (
    <div className="flex gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={result.rows.length === 0}
        onClick={() => exportToCsv(result.rows, result.columns, endpointName)}
      >
        Export CSV
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={result.rows.length === 0}
        onClick={() => exportToJson(result.rows, endpointName)}
      >
        Export JSON
      </Button>
    </div>
  );
}