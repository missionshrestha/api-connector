// frontend/src/features/data-preview/components/DataPreviewTable.tsx
import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { PreviewResult } from "../types";
import { CellRenderer } from "./CellRenderer";
import { ColumnHeaderTooltip } from "./ColumnHeaderTooltip";

const ROWS_PER_PAGE = 10;
const ROW_LIMIT_OPTIONS = [10, 25, 50, 100] as const;

interface DataPreviewTableProps {
  result: PreviewResult;
  rowLimit: number;
  onRowLimitChange: (limit: number) => void;
  isRefetching: boolean;
}

export function DataPreviewTable({
  result,
  rowLimit,
  onRowLimitChange,
  isRefetching,
}: DataPreviewTableProps) {
  const [currentPage, setCurrentPage] = useState(1);

  const totalRows = result.rows.length;
  const totalPages = Math.ceil(totalRows / ROWS_PER_PAGE);
  const startIdx = (currentPage - 1) * ROWS_PER_PAGE;
  const endIdx = Math.min(startIdx + ROWS_PER_PAGE, totalRows);
  const visibleRows = result.rows.slice(startIdx, endIdx);

  function handleRowLimitChange(val: string) {
    const limit = Number(val);
    setCurrentPage(1); // reset to page 1 on re-fetch
    onRowLimitChange(limit);
  }

  return (
    <div className="space-y-4">
      {/* Controls row */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>
            Showing {startIdx + 1}–{endIdx} of {totalRows} row
            {totalRows !== 1 ? "s" : ""}
            {result.has_more && " (more available)"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Rows to fetch:</span>
          <Select
            value={String(rowLimit)}
            onValueChange={handleRowLimitChange}
            disabled={isRefetching}
          >
            <SelectTrigger className="w-20 h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROW_LIMIT_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isRefetching && (
            <span className="text-xs text-muted-foreground animate-pulse">
              Fetching…
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-muted/50 sticky top-0">
            <tr>
              {result.columns.map((col) => (
                <th
                  key={col.key_path}
                  className="px-3 py-2 text-left border-b border-border whitespace-nowrap"
                >
                  <ColumnHeaderTooltip column={col} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                className="border-b border-border/50 hover:bg-muted/10 transition-colors"
              >
                {result.columns.map((col) => (
                  <td key={col.key_path} className="px-3 py-2 max-w-xs align-top">
                    <CellRenderer
                      value={row[col.name]}
                      effectiveType={col.effective_type}
                    />
                  </td>
                ))}
              </tr>
            ))}
            {visibleRows.length === 0 && (
              <tr>
                <td
                  colSpan={result.columns.length || 1}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  No rows returned.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {currentPage} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={currentPage >= totalPages}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}