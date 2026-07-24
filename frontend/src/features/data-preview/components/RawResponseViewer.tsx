// frontend/src/features/data-preview/components/RawResponseViewer.tsx
import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import type { ResponseFormat } from "@/shared/types";

interface RawResponseViewerProps {
  body: string; // JSON or XML string, may be truncated at 50KB
  format?: ResponseFormat | undefined; // defaults to "json", preserving prior behavior
}

/**
 * Minimal JSON syntax highlighting using inline <span> elements.
 * Avoids Prism.js / Monaco to keep bundle size small.
 *
 * SECURITY: HTML entities MUST be escaped before syntax highlighting.
 * API responses may contain "</span><script>..." as literal JSON string values.
 * The escape step neutralizes these before the regex substitutions inject <span> tags.
 */
function highlightJson(raw: string): string {
  // Step 1: Escape HTML entities first (XSS prevention)
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Step 2: Apply token coloring (safe now that < > are escaped)
  return escaped
    .replace(
      /("(?:[^"\\]|\\.)*")\s*:/g,
      '<span class="text-blue-600 dark:text-blue-400">$1</span>:',
    )
    .replace(
      /:\s*("(?:[^"\\]|\\.)*")/g,
      ': <span class="text-green-600 dark:text-green-400">$1</span>',
    )
    .replace(
      /\b(true|false)\b/g,
      '<span class="text-purple-600 dark:text-purple-400">$1</span>',
    )
    .replace(/\bnull\b/g, '<span class="text-gray-500">null</span>')
    .replace(
      /(?<!["\w])\b(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b(?!["\w])/g,
      '<span class="text-amber-600 dark:text-amber-400">$1</span>',
    );
}

/**
 * Minimal XML syntax highlighting using inline <span> elements.
 * Structurally mirrors highlightJson: escape first, color tokens second.
 *
 * SECURITY: HTML entities MUST be escaped before syntax highlighting, for the
 * same reason as highlightJson — XML text/attribute content is externally
 * sourced and may contain "</span><script>..." as literal text.
 */
function highlightXml(raw: string): string {
  // Step 1: Escape HTML entities first (XSS prevention) — identical to highlightJson
  const escaped = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Step 2: Apply token coloring (safe now that < > are escaped). Only tags
  // starting with a letter after &lt; or &lt;/ are matched, so XML
  // declarations/comments/CDATA fall through unhighlighted (still escaped).
  return escaped.replace(/&lt;\/?[A-Za-z_][\s\S]*?&gt;/g, (tag) => {
    // Attribute name="value" pairs — processed on the raw tag text first,
    // before any <span> is injected, so this pass can't re-match markup
    // injected by the tag-name pass below.
    let colored = tag.replace(
      /(\s)([A-Za-z_][\w.:-]*)(=)"([^"]*)"/g,
      (_m, ws, name, eq, val) =>
        `${ws}<span class="text-blue-600 dark:text-blue-400">${name}</span>${eq}"<span class="text-green-600 dark:text-green-400">${val}</span>"`,
    );
    // Element tag name — anchored to the start of the tag, so it can only
    // match the real tag name, never text inside the attribute spans above.
    colored = colored.replace(
      /^(&lt;\/?)([A-Za-z_][\w.:-]*)/,
      '$1<span class="text-blue-600 dark:text-blue-400">$2</span>',
    );
    return colored;
  });
}

type ViewerHeight = "compact" | "expanded";

export function RawResponseViewer({ body, format = "json" }: RawResponseViewerProps) {
  const [copied, setCopied] = useState(false);
  const [height, setHeight] = useState<ViewerHeight>("compact");

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available in HTTP contexts — fail silently
    }
  }

  const highlighted = format === "xml" ? highlightXml(body) : highlightJson(body);
  const isTruncated = body.length >= 50_000;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Raw Response (last page)</span>
          {isTruncated && (
            <span className="text-xs text-amber-600 dark:text-amber-400">
              (truncated at 50KB)
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setHeight((h) => (h === "compact" ? "expanded" : "compact"))}
          >
            {height === "compact" ? "Expand" : "Collapse"}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={handleCopy}>
            {copied ? "Copied!" : "Copy"}
          </Button>
        </div>
      </div>

      <div
        className={`overflow-auto rounded-lg bg-muted border border-border transition-all ${
          height === "compact" ? "max-h-48" : "max-h-[70vh]"
        }`}
      >
        <pre
          className="p-3 text-xs font-mono whitespace-pre-wrap break-words"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </div>
    </div>
  );
}