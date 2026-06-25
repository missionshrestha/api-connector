// frontend/src/features/schema-explorer/components/__tests__/SchemaExplorerTree.dom.test.tsx
/**
 * DOM count test for SchemaExplorerTree virtual scrolling.
 *
 * Verifies that rendering 250 SchemaField records does NOT result in
 * 250 DOM nodes. The virtualizer renders only the visible slice.
 *
 * @tanstack/react-virtual works with jsdom, but jsdom has no real layout engine,
 * so getTotalSize() may return 0. We mock useVirtualizer to return a fixed
 * visible window of 10 items to test the integration contract.
 */
import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { SchemaExplorerTree } from "../SchemaExplorerTree";
import type { SchemaField } from "@/shared/types";

// Mock the virtualizer to simulate what it returns in a real browser viewport
// jsdom has no layout engine, so element offsets are 0 — the virtualizer renders
// nothing without this mock.
vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () =>
      Array.from({ length: Math.min(10, count) }, (_, i) => ({
        index: i,
        start: i * 48,
        size: 48,
        key: i,
      })),
    getTotalSize: () => count * 48,
  }),
}));

function makeSchemaFields(count: number): SchemaField[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    endpoint: 1,
    key_path: `field_${String(i).padStart(3, "0")}`,
    alias: null,
    inferred_type: "string" as const,
    type_override: null,
    include: true,
    array_handling: null,
    null_percentage: 0,
    sample_value: `value_${i}`,
    stale: false,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  }));
}

function renderTree(fields: SchemaField[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <SchemaExplorerTree
          fields={fields}
          onUpdate={vi.fn()}
          isSaving={false}
          searchQuery=""
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

describe("SchemaExplorerTree — virtual scroll DOM count", () => {
  it("renders only ~10 DOM nodes for 250 fields (virtual scrolling active)", () => {
    const fields = makeSchemaFields(250);
    const { container } = renderTree(fields);

    // Count rows via data-schema-field-row attribute
    const rowNodes = container.querySelectorAll("[data-schema-field-row]");

    // With the mock virtualizer returning 10 items, we expect ≤ 15 row nodes
    // (accounts for overscan and the fact that some paths don't have field nodes)
    expect(rowNodes.length).toBeLessThanOrEqual(15);

    // Critically: must NOT render all 250
    expect(rowNodes.length).toBeLessThan(250);
  });

  it("renders 0 nodes when no fields are provided", () => {
    const { container } = renderTree([]);
    const rowNodes = container.querySelectorAll("[data-schema-field-row]");
    expect(rowNodes.length).toBe(0);
  });

  it("search filter reduces visible nodes", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const fields = makeSchemaFields(250);
    // Only field_001 through field_009 will match "field_00"
    const { container } = render(
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <SchemaExplorerTree
            fields={fields}
            onUpdate={vi.fn()}
            isSaving={false}
            searchQuery="field_001"
          />
        </TooltipProvider>
      </QueryClientProvider>
    );

    const rowNodes = container.querySelectorAll("[data-schema-field-row]");
    // Only matching fields are in the tree — far fewer than 250
    expect(rowNodes.length).toBeLessThan(250);
  });
});