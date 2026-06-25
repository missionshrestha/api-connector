// frontend/src/features/data-preview/api/exportUtils.ts
import type { PreviewColumnMeta } from "../types";

function formatDateForFilename(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

function sanitizeForFilename(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Escape a single CSV cell value.
 * - Always wraps in double quotes (RFC 4180 compliant)
 * - Escapes internal double quotes by doubling them: " → ""
 * - null/undefined → empty string (not the word "null")
 * - Objects/arrays → JSON stringified before wrapping
 *
 * Without this: a value like "Smith, John" with an internal comma
 * would split into two columns, corrupting every subsequent column.
 */
function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '""';
  let str: string;
  if (typeof value === "object") {
    str = JSON.stringify(value);
  } else {
    str = String(value);
  }
  return `"${str.replace(/"/g, '""')}"`;
}

function triggerDownload(content: string, mimeType: string, filename: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  // Revoke after short delay to allow browser to start the download
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

export function exportToCsv(
  rows: Array<Record<string, unknown>>,
  columns: PreviewColumnMeta[],
  endpointName: string,
): void {
  const headers = columns.map((c) => escapeCsvCell(c.name));
  const dataRows = rows.map((row) =>
    columns.map((col) => escapeCsvCell(row[col.name])).join(","),
  );
  const csv = [headers.join(","), ...dataRows].join("\n");
  const filename = `${sanitizeForFilename(endpointName)}-preview-${formatDateForFilename(new Date())}.csv`;
  triggerDownload(csv, "text/csv;charset=utf-8;", filename);
}

export function exportToJson(
  rows: Array<Record<string, unknown>>,
  endpointName: string,
): void {
  const json = JSON.stringify(rows, null, 2);
  const filename = `${sanitizeForFilename(endpointName)}-preview-${formatDateForFilename(new Date())}.json`;
  triggerDownload(json, "application/json;charset=utf-8;", filename);
}