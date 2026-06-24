// frontend/src/features/schema-explorer/components/SchemaExplorerTree.tsx
import { useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { SchemaField } from "@/shared/types";
import { SchemaFieldRow } from "./SchemaFieldRow";
import type { UpdateSchemaFieldRequest } from "../api/schemaApi";

// ── Tree types ────────────────────────────────────────────────────────────────

interface TreeNode {
  path: string;       // Full dot-notation path
  label: string;      // Last path segment (display label)
  depth: number;
  field?: SchemaField;
  children: TreeNode[];
}

// ── Tree builder ──────────────────────────────────────────────────────────────

function buildTree(fields: SchemaField[]): TreeNode[] {
  const sorted = [...fields].sort((a, b) => a.key_path.localeCompare(b.key_path));
  const nodeMap = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  for (const field of sorted) {
    const segments = field.key_path.split(".");

    // Ensure all intermediate ancestor nodes exist
    for (let i = 0; i < segments.length - 1; i++) {
      const ancestorPath = segments.slice(0, i + 1).join(".");
      if (!nodeMap.has(ancestorPath)) {
        const ancestorNode: TreeNode = {
          path: ancestorPath,
          label: segments[i]!,
          depth: i,
          children: [],
        };
        nodeMap.set(ancestorPath, ancestorNode);

        // Attach to grandparent or root
        const grandParentPath = segments.slice(0, i).join(".");
        if (grandParentPath && nodeMap.has(grandParentPath)) {
          nodeMap.get(grandParentPath)!.children.push(ancestorNode);
        } else if (!grandParentPath) {
          roots.push(ancestorNode);
        }
      }
    }

    // Final segment — create or update the node with the actual field
    const finalPath = field.key_path;
    const finalDepth = segments.length - 1;

    if (nodeMap.has(finalPath)) {
      // Node was pre-created as an intermediate group — assign the field
      nodeMap.get(finalPath)!.field = field;
    } else {
      const node: TreeNode = {
        path: finalPath,
        label: segments[finalDepth]!,
        depth: finalDepth,
        field,
        children: [],
      };
      nodeMap.set(finalPath, node);

      const parentPath = segments.slice(0, -1).join(".");
      if (parentPath && nodeMap.has(parentPath)) {
        nodeMap.get(parentPath)!.children.push(node);
      } else {
        roots.push(node);
      }
    }
  }

  return roots;
}

// ── Flatten tree to visible items ──────────────────────────────────────────────

interface FlatItem {
  node: TreeNode;
  depth: number;
  isExpandable: boolean;
}

function flattenVisible(nodes: TreeNode[], expanded: Set<string>): FlatItem[] {
  const items: FlatItem[] = [];

  function walk(nodeList: TreeNode[]) {
    for (const node of nodeList) {
      const isExpandable = node.children.length > 0;
      items.push({ node, depth: node.depth, isExpandable });
      if (isExpandable && expanded.has(node.path)) {
        walk(node.children);
      }
    }
  }

  walk(nodes);
  return items;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface SchemaExplorerTreeProps {
  fields: SchemaField[];
  onUpdate: (fieldId: number, data: UpdateSchemaFieldRequest) => void;
  isSaving: boolean;
  searchQuery: string;
}

export function SchemaExplorerTree({
  fields,
  onUpdate,
  isSaving,
  searchQuery,
}: SchemaExplorerTreeProps) {
  "use no memo"; // TanStack Virtual's useVirtualizer is incompatible with React Compiler memoization

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // All non-leaf paths start expanded
  const allNonLeafPaths = useMemo(() => {
    const paths = new Set<string>();
    for (const f of fields) {
      const segments = f.key_path.split(".");
      for (let i = 0; i < segments.length - 1; i++) {
        paths.add(segments.slice(0, i + 1).join("."));
      }
    }
    return paths;
  }, [fields]);

  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(allNonLeafPaths);

  function toggleExpand(path: string) {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  // Filter by search query
  const filteredFields = useMemo(() => {
    if (!searchQuery.trim()) return fields;
    const q = searchQuery.toLowerCase();
    return fields.filter(
      (f) =>
        f.key_path.toLowerCase().includes(q) ||
        (f.alias?.toLowerCase().includes(q) ?? false),
    );
  }, [fields, searchQuery]);

  const tree = useMemo(() => buildTree(filteredFields), [filteredFields]);

  const flatItems = useMemo(
    () => flattenVisible(tree, expandedPaths),
    [tree, expandedPaths],
  );

  // ⚠️ CRITICAL: scroll container MUST have explicit height + overflow-y: auto
  // Without it, getTotalSize() returns 0 and no rows render at all.
  // eslint-disable-next-line react-hooks/incompatible-library -- useVirtualizer is incompatible with React Compiler; component opts out via "use no memo" above
  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => 48, // Must match SchemaFieldRow height (h-12 = 48px)
    overscan: 5,
  });

  if (flatItems.length === 0 && searchQuery) {
    return (
      <div className="py-8 text-center text-muted-foreground text-sm">
        No fields match &apos;{searchQuery}&apos;.
      </div>
    );
  }

  return (
    <div
      ref={scrollContainerRef}
      style={{ height: "600px", overflowY: "auto" }}
      className="border border-border rounded-lg"
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const item = flatItems[virtualRow.index];
          if (!item) return null;
          const { node, depth, isExpandable } = item;

          return (
            <div
              key={node.path}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: `${virtualRow.size}px`,
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {node.field ? (
                <SchemaFieldRow
                  field={node.field}
                  depth={depth}
                  onUpdate={onUpdate}
                  isSaving={isSaving}
                  isExpandable={isExpandable}
                  isExpanded={expandedPaths.has(node.path)}
                  onToggleExpand={() => toggleExpand(node.path)}
                />
              ) : (
                // Group node without a field (intermediate path with no own SchemaField)
                <div
                  className="flex items-center h-12 px-2 border-b border-border/30 bg-muted/10 cursor-pointer hover:bg-muted/20"
                  style={{ paddingLeft: `${8 + depth * 16}px` }}
                  onClick={() => toggleExpand(node.path)}
                >
                  <span className="text-xs text-muted-foreground mr-1.5">
                    {expandedPaths.has(node.path) ? "▾" : "▸"}
                  </span>
                  <span className="text-sm font-mono font-medium">{node.label}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    ({node.children.length} fields)
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}