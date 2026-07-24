// frontend/src/features/data-preview/components/__tests__/RawResponseViewer.dom.test.tsx
/**
 * Covers RawResponseViewer's format-aware highlighting (P4.A-03):
 * XML tag/attribute coloring, the JSON path's byte-for-byte regression,
 * and the XSS-prevention contract both highlighters share (escape before
 * injecting <span> markup, since the body is dangerouslySetInnerHTML'd).
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { RawResponseViewer } from "../RawResponseViewer";

function renderViewer(body: string, format?: "json" | "xml") {
  return render(<RawResponseViewer body={body} format={format} />);
}

describe("RawResponseViewer — XML highlighting (P4.A-03)", () => {
  it("colors element tag names and attribute name/value pairs for format=\"xml\"", () => {
    const xml = `<record id="42"><title>Bach</title></record>`;
    const { container } = renderViewer(xml, "xml");
    const pre = container.querySelector("pre")!;

    // Tag names and the attribute name are colored blue.
    expect(pre.querySelectorAll(".text-blue-600").length).toBeGreaterThanOrEqual(4);
    // The attribute's quoted value is colored green.
    const greenSpans = Array.from(pre.querySelectorAll(".text-green-600"));
    expect(greenSpans.some((el) => el.textContent === "42")).toBe(true);

    // Renders as XML, not JSON — no JSON-only token classes present.
    expect(pre.querySelector(".text-purple-600")).toBeNull(); // JSON booleans
  });

  it("format=\"json\" and omitted format produce byte-for-byte identical output (regression)", () => {
    // Pre-existing highlightJson path is untouched by this phase — this only
    // proves the new format branch doesn't alter its behavior, not that
    // highlightJson's own output is bug-free (it is not — see implementation.md).
    const jsonBody = JSON.stringify({ a: 1, ok: true, name: "x" });
    const withFormat = renderViewer(jsonBody, "json");
    const omitted = renderViewer(jsonBody, undefined);

    expect(withFormat.container.querySelector("pre")!.innerHTML).toBe(
      omitted.container.querySelector("pre")!.innerHTML,
    );
  });

  it("escapes an XSS payload in XML element text content instead of executing it", () => {
    const xml = `<note>${"</span><script>window.__xss = true;</script>"}</note>`;
    const { container } = renderViewer(xml, "xml");

    // No live <script> element was injected into the DOM — the payload's
    // literal "<"/">" were escaped before any <span> markup was added, so
    // dangerouslySetInnerHTML never sees an unescaped script tag.
    expect(container.querySelector("script")).toBeNull();
  });

  it("escapes an XSS payload in an XML attribute value instead of executing it", () => {
    const xml = `<record note="${"</span><script>window.__xss = true;</script>"}"></record>`;
    const { container } = renderViewer(xml, "xml");

    expect(container.querySelector("script")).toBeNull();
  });
});
