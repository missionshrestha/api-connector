# Frontend & End-to-End Validation — Breakdown

Feature: `001-xml-response-support` · Phase 4 of 4: Frontend & End-to-End Validation
Branch: `001-xml-response-support` · Generated against commit `78d2d79e839d43124c77d304202299bb144393b4`
Previous phase: Phase 3 (Schema Inference & Data Preview Integration) — Reconciled 🟡 YELLOW, committed. Confirmed reality: backend is now fully functional for XML endpoints via direct API calls — `PaginationEngine.paginate()` branches on `endpoint.response_format` (Phase 2), `DataPreviewService.raw_response_body` returns the original XML text for XML-configured endpoints via the `raw_response_sink` out-parameter (Phase 3), and `SchemaInferenceEngine`/all 3 body-reading pagination strategies are proven to need zero XML-aware changes. One carried-forward, pre-existing, format-agnostic bug is still live and unfixed: `PaginationEngine._request_with_retry` drops the query string on the `_next_url` sentinel path (`engine.py:123-126`), affecting `NextURLStrategy`/`LinkHeaderStrategy` for JSON exactly as much as XML endpoints (§9 of `project-detail.md`, DEV-1 in Phase 3's reconciliation).
Next phase: none — this is the final phase of `001-xml-response-support` (`plan.md` §7).
Source: `plan.md` §8 Phase 4

---

## 1. Phase Context

**Purpose & Outcome**: Close out the feature by (a) surfacing `response_format` in the endpoint form and rendering XML raw-response text as XML instead of JSON, and (b) proving the entire pipeline — connection test → configure → infer → preview — against a real, namespaced public XML API, entirely through the UI. Outcome: the feature is fully shippable to end users (`plan.md` §9 "After Phase 4" milestone); `requirement.md` §5's SC1-SC8 all hold against the completed feature.

**Dependencies**: Needs Phase 3's fully functional backend (confirmed above). Produces: user-facing completion of the feature — no further phase consumes this one's output.

**Scope calibration note**: Lean-to-standard. 6 atomic tasks across 2 subphases, 1 `[REVIEW-GATE]` (P4.B, carried from `plan.md`), 0 `[IRREVERSIBLE]` tasks — under the escalation threshold. P4.A is small, mechanical UI plumbing (the backend contract it surfaces was fully built and tested in Phases 2-3); P4.B is not code at all — it is a supervised, real-network validation run plus a documentation addendum, gated because it is "not fully reproducible/deterministic like the rest of the test suite" (`plan.md` §8).

**Already resolved by reading the current code, not left as open questions**:

1. **No frontend code depends on `PaginationEngineError`'s old hard-coded "non-JSON" wording.** Grepped `frontend/src/` for `"non-JSON"` / `PaginationEngineError` / `"could not be parsed"` — zero matches. The format-aware message change (Phase 2) is a non-issue for this phase, closing out the carry-forward note from Phase 2/3's reconciliations. No task added for this.
2. **The frontend `Endpoint` domain type and endpoint form currently have zero `response_format` surface** — confirmed by reading `frontend/src/shared/types/domain.ts`, `frontend/src/features/endpoint/schemas/endpointSchema.ts`, `frontend/src/features/endpoint/api/endpointApi.ts`, and `frontend/src/features/endpoint/pages/EndpointFormPage.tsx` directly. The backend has exposed `response_format` on all three `Endpoint` serializers since Phase 2 (`serializers/endpoint.py:58,103,196`) — the frontend simply never picked it up. This is exactly the gap P4.A closes.
3. **`RawResponseViewer` unconditionally JSON-highlights `body`** (`RawResponseViewer.tsx:17-43`) with no format awareness at all — confirmed by reading the file directly. `DataPreviewPage.tsx:197` calls it with only `body={preview.data.raw_response_body}`, no format information passed. P4.A's remaining tasks close this gap.

---

## 2. Open Decisions

**OD-1: Which public XML API (and which pagination strategy) does P4.B's end-to-end validation target?**

Context: `plan.md` §8 Phase 4 defers the exact target to task level ("pick one that's stable/free and genuinely namespaced, not a toy example"). Separately, Phase 3's reconciliation carried forward a live concern: `PaginationEngine._request_with_retry` drops the query string on the `_next_url` sentinel path (`engine.py:123-126`), affecting `NextURLStrategy`/`LinkHeaderStrategy`. If P4.B's target/strategy combination exercises either of those two strategies with a query-string-bearing next-page URL, the e2e run fails on this pre-existing, out-of-feature bug instead of anything this feature built — `project-detail.md` Open Question #5 flags exactly this risk.

Options considered:
- **(a) [RECOMMENDED] Target the Deutsche Nationalbibliothek SRU endpoint (`services.dnb.de/sru/dnb`), the same real, live, unauthenticated API Phase 1's spike already fetched `sample.xml` from — using `CursorStrategy`, not `NextURL`/`LinkHeader`.** SRU's own protocol is a `startRecord`/`maximumRecords` cursor advance: the real captured `sample.xml` (confirmed by reading it directly) contains `numberOfRecords` (`111225`) and `nextRecordPosition` (`4`) as direct children of the root `searchRetrieveResponse` element, and Phase 3's own `test_schema_inference.py:37` already confirms and reuses the exact real data-root path `searchRetrieveResponse.records.record` against this same sample. This means `data_root_path`, `record_count_path`, and `cursor_response_path` are all already proven against real data, not guessed: `data_root_path = "searchRetrieveResponse.records.record"`, `record_count_path = "searchRetrieveResponse.numberOfRecords"`, `cursor_response_path = "searchRetrieveResponse.nextRecordPosition"`, `cursor_request_param = "startRecord"` (the SRU-standard request parameter). Neither `NextURLStrategy` nor `LinkHeaderStrategy` is touched, so the DEV-1 bug is structurally avoided, not just dodged by luck. No auth required (matches the "No Auth — JSONPlaceholder" pattern already in `docs/e2e-testing-guide.md` §2).
- **(b) Fix the DEV-1 `_next_url` bug first, as a preliminary task, then pick any target freely (including one needing `NextURL`/`LinkHeader`).** More thorough (exercises the previously-untested strategies against XML too), but expands this phase's scope to a pre-existing, format-agnostic bug fix that predates `001-xml-response-support` entirely and affects JSON endpoints identically — a drive-by fix inconsistent with Rule 3's "touch nothing beyond what the phase requires," and it was explicitly deferred out of Phase 3 for this reason.
- **(c) Pick a different, new public XML API not yet touched by this pipeline.** Loses the "already real, already fetched successfully, already proven against the exact real bytes" advantage option (a) has; introduces a fresh unknown (rate limits, auth, response quirks) for no stated benefit over reusing a source this feature has already validated end-to-end at the parsing layer.

Recommendation: (a), weighed against the Decision Priority Order — **Business value / Correctness** (validates the actual target use case, government/public-data SRU APIs, per `requirement.md` §5 stakeholder note); **Reliability** (avoids a known, already-diagnosed bug entirely rather than hoping the chosen target's next-page URLs happen to lack a query string); **Maintainability** (reuses already-proven paths from Phase 1/3 instead of re-deriving new ones). DEV-1 itself is not fixed by this recommendation — it is recorded as a still-open, still-out-of-scope defect (see `project-detail.md` §9/§11); if the human prefers option (b), P4.B-01 below needs a preliminary "fix `_request_with_retry`'s params handling" task inserted before it. Tied to subphase **P4.B `[REVIEW-GATE]`** — confirm before P4.B-01 is executed; the tasks below are written against option (a).

---

## 3. Subphases & Atomic Tasks

### P4.A — UI Surfacing

**Objective**: Expose `response_format` end-to-end through the frontend (type mirror → form → submission) and make `RawResponseViewer` format-aware, so an XML-configured endpoint's raw response renders as XML rather than being JSON-highlighted.
**Deliverables**: `Endpoint`/request type updates, endpoint form Select control + defaulting, XML-aware `RawResponseViewer`, `DataPreviewPage` wiring.
**Complexity/risk**: Low. Purely additive frontend surface over an already-complete, already-tested backend contract (Phase 2/3). The one place worth care is `RawResponseViewer`'s new XML branch, which must preserve the file's existing HTML-escape-before-highlight convention — the module's own docstring already documents why (API response bodies can contain literal `</span><script>...`), and that threat model applies identically to XML text content.

```
Task ID:                  P4.A-01
Title:                    Mirror response_format in frontend types and API request shapes  [P]
Description:              Add `response_format` to 3 frontend files, mirroring the backend
                          shape confirmed in `serializers/endpoint.py:58,103,196` and
                          `models/enums.py:46-48` (`ResponseFormat.JSON = "json"`,
                          `ResponseFormat.XML = "xml"`):
                          (1) `frontend/src/shared/types/domain.ts`: add
                          `export type ResponseFormat = "json" | "xml";` alongside the
                          existing enum mirrors (`AuthType`, `PaginationStrategy`, etc.,
                          lines 4-34), and add `response_format: ResponseFormat;` to the
                          `Endpoint` interface (line 63-79), positioned after
                          `endpoint_headers` matching the backend field's own position in
                          `EndpointReadSerializer.Meta.fields`.
                          (2) `frontend/src/features/endpoint/api/endpointApi.ts`: add
                          `response_format?: ResponseFormat;` to `EndpointCreateRequest`
                          (line 5-15), matching the existing optional-field style already
                          used there (`data_root_path?`, `record_count_path?`) —
                          `EndpointUpdateRequest` inherits it automatically via
                          `Partial<EndpointCreateRequest>` (line 17).
                          (3) `frontend/src/features/endpoint/schemas/endpointSchema.ts`:
                          add `response_format: z.enum(["json", "xml"])` to the zod object
                          (after `endpoint_headers`, before `data_root_path`), following
                          the file's existing `z.enum(["GET", "POST"])` pattern for
                          `method` (line 8).
Why This Matters:         Every later task in this phase (the form Select, the
                          RawResponseViewer format branch, the DataPreviewPage wiring)
                          needs this type to exist first — without it, `endpoint.response_format`
                          is a TypeScript error everywhere it's read, and the create/update
                          payload has no typed slot to carry the user's chosen value.
Dependencies:             None
Inputs/Preconditions:     `backend/api_connector/serializers/endpoint.py` (confirmed,
                          `response_format` in all 3 serializers' `Meta.fields`);
                          `backend/api_connector/models/enums.py:46-48` (confirmed,
                          `ResponseFormat` TextChoices values `"json"`/`"xml"`).
Output/Artifact:          `response_format` present and correctly typed in `Endpoint`,
                          `EndpointCreateRequest`, `EndpointUpdateRequest`, and
                          `endpointSchema`'s zod object; verifiable by
                          `npm run typecheck --prefix frontend` passing with zero new
                          errors anywhere these types are consumed.
Placeholders:             None
Decision Type:            [REVERSIBLE] — additive type/schema fields; no runtime behavior
                          change until P4.A-02 wires a UI control to them.
Security & Observability: N/A — type-level change only, no runtime code path.
Testing Notes:            Extend `frontend/src/shared/types/domain.test.ts` (the
                          established type-only-test file, `expectTypeOf` pattern already
                          used for `AuthType`/`ConnectionTestResult`) with an assertion
                          that `Endpoint["response_format"]` equals the literal union
                          `"json" | "xml"` — not a bare `string` — mirroring the file's
                          existing "not just a literal" checks (e.g. the `ErrorCode`
                          assertions, lines 29-36). No behavioral/DOM test needed for a
                          type-only change.
```

```
Task ID:                  P4.A-02
Title:                    Add response_format Select to EndpointFormPage
Description:              In `frontend/src/features/endpoint/pages/EndpointFormPage.tsx`:
                          add a `response_format` field to the form, following the existing
                          `Method` Select's exact pattern (lines 228-239: a `Select` bound
                          via `useWatch`/an `onValueChange` handler, not a `Controller`),
                          placed in the "Endpoint Configuration" section near `Method` or
                          `Data Root Path`. Two `SelectItem`s: `json` → "JSON", `xml` →
                          "XML". Wire it into `useForm`'s `defaultValues` (initial value
                          `"json"`, matching the model's own default) and into the
                          edit-mode `reset()` call (line 107-118, add
                          `response_format: endpoint.response_format`) so an existing
                          endpoint's persisted value round-trips exactly like every other
                          field in that block. `onSubmit`'s `data` object already flows
                          straight into `createEndpoint.mutate(data, ...)` /
                          `updateEndpoint.mutate({ endpointId, data }, ...)` (lines 137-153)
                          — no change needed there once `EndpointFormValues` includes the
                          field (P4.A-01).
                          **Create-mode default, to honor SC1 without duplicating backend
                          logic**: fetch the parent `ConnectionProfile` via the existing
                          `useProfile(profileId)` hook (`@/features/connection-profile/hooks`,
                          confirmed exported, `enabled: id !== undefined`). Once it resolves
                          (create mode only, i.e. `!isEditMode`), if the user has not already
                          touched the field (`!formState.dirtyFields.response_format`), call
                          `setValue("response_format", profile.last_test_detected_format === "xml" ? "xml" : "json")`
                          — mirroring the exact fallback rule `views/endpoint.py:116-120`
                          already implements server-side (only exact `"json"`/`"xml"` count;
                          everything else, including `null`, falls back to `"json"`). This is
                          a **[ASSUMPTION]**: it duplicates a one-line server-side fallback
                          on the client purely so the Select visibly shows the
                          soon-to-be-actual default before submit, rather than the
                          alternative of omitting the field from the create payload
                          entirely and letting the backend resolve it invisibly. What
                          changes if wrong: if the human prefers the field to start blank/
                          "auto" and only be sent when the user explicitly picks a value,
                          `response_format` becomes optional in the zod schema and is
                          conditionally omitted from the submitted `data` — a REVISE to
                          this task, not a different task.
Why This Matters:         FR8/SC1 require the endpoint form to expose `response_format` for
                          both viewing and editing — today it is invisible in the UI even
                          though the backend has fully supported it since Phase 2; a user
                          configuring an XML endpoint currently has no way to confirm or
                          correct the detected format without calling the API directly.
Dependencies:             P4.A-01
Inputs/Preconditions:     `EndpointFormPage.tsx`'s existing `Method` Select (confirmed,
                          lines 228-239) and `reset()` call (confirmed, lines 105-119);
                          `useProfile` (confirmed, exported from
                          `frontend/src/features/connection-profile/hooks/useProfiles.ts:29-32`).
Output/Artifact:          A `response_format` Select control in the endpoint form that (a)
                          defaults to the parent profile's detected format on create, (b)
                          shows the persisted value on edit, and (c) is user-editable in
                          both modes; verifiable by creating/editing an endpoint and
                          confirming the submitted request body carries the selected value.
Placeholders:             None
Decision Type:            [REVERSIBLE] — the create-mode defaulting mechanism (see
                          Description's `[ASSUMPTION]`) is a UI convenience, fully
                          replaceable without touching any other task.
Security & Observability: `response_format` is not secret/PII; no new logging needed. The
                          Select constrains input to exactly `"json"`/`"xml"` client-side;
                          the server independently re-validates via DRF's `ChoiceField`
                          regardless (defense in depth already exists, nothing new required
                          here).
Testing Notes:            Given this codebase's very thin frontend test coverage (no
                          existing form-interaction tests to extend — `project-detail.md`
                          §7 Testing), a manual check is acceptable: (1) create an endpoint
                          under a profile whose `last_test_detected_format` is `"xml"` →
                          Select shows "XML" before submit, editable to "JSON"; (2) create
                          under a profile with no test run yet (`last_test_detected_format`
                          is `null`) → Select shows "JSON"; (3) edit an existing XML
                          endpoint → Select shows its persisted value, not the profile's
                          current detected format; (4) change the value on an existing
                          endpoint and save → PATCH payload reflects the change.
```

```
Task ID:                  P4.A-03
Title:                    RawResponseViewer renders XML with XML-appropriate highlighting  [P]
Description:              In `frontend/src/features/data-preview/components/RawResponseViewer.tsx`:
                          add a `format?: ResponseFormat` prop to `RawResponseViewerProps`
                          (default to `"json"` if omitted, preserving today's behavior for
                          every existing, un-updated call site). Add a new
                          `highlightXml(raw: string): string` function, structurally
                          mirroring `highlightJson`'s existing shape exactly (lines 17-43):
                          **Step 1 — escape HTML entities first, identical to
                          `highlightJson`'s Step 1 and its stated rationale** (the module's
                          own docstring: "API responses may contain
                          `</span><script>...` as literal string values" — this threat
                          model applies just as much to XML text/attribute content as to
                          JSON string values). **Step 2 — token-color XML constructs** using
                          the same Tailwind color classes already in use, for visual
                          consistency: element tag names (open `<tag`/close `</tag>`, the
                          angle brackets themselves need not be colored) in the same blue
                          used for JSON keys; attribute names in the same blue; attribute
                          quoted-string values in the same green used for JSON string
                          values. XML comments/CDATA/processing instructions do not need
                          their own token class — plain (unhighlighted, but still escaped)
                          text is an acceptable, non-over-engineered fallback for those,
                          consistent with Rule 4. In the component body, branch on
                          `format`: `format === "xml" ? highlightXml(body) : highlightJson(body)`.
                          Update the label text (currently hard-coded "Raw Response (last
                          page)", line 68) to stay format-neutral — no code change needed
                          there since the wording already doesn't claim JSON specifically.
Why This Matters:         SC6/DEC-6 require the raw XML response to be shown as what it
                          actually is; `DataPreviewService` has returned the real XML text
                          in `raw_response_body` since Phase 3, but today's viewer would
                          run XML text through a JSON-shaped highlighter, which either
                          produces incorrect/no coloring or (worse, given the module's own
                          documented threat model) could miscolor around unescaped-looking
                          constructs if the escape step were skipped when adding the new
                          branch.
Dependencies:             P4.A-01 (for the `ResponseFormat` type import)
Inputs/Preconditions:     `RawResponseViewer.tsx`'s current `highlightJson` (confirmed,
                          lines 17-43) and its documented XSS-prevention rationale
                          (confirmed, lines 9-16).
Output/Artifact:          `RawResponseViewer` renders XML text with XML-appropriate,
                          HTML-escaped-first syntax highlighting when `format="xml"`, and
                          is byte-for-byte unchanged in behavior for `format="json"`/
                          omitted `format`; verifiable by rendering the component with a
                          real XML string (e.g. Phase 1's `sample.xml` contents) and
                          inspecting the output markup.
Placeholders:             None
Decision Type:            [REVERSIBLE] — additive prop with a JSON-preserving default;
                          zero effect on any caller that doesn't pass `format`.
Security & Observability: **This task's one real risk**: the new `highlightXml` function
                          MUST escape HTML entities before injecting any `<span>` markup,
                          exactly like `highlightJson` does — an XML response body is
                          externally-sourced, potentially-untrusted content rendered via
                          `dangerouslySetInnerHTML` (line 97, unchanged), so skipping the
                          escape step on the new branch would reintroduce the exact
                          stored/reflected-content XSS vector the existing function's own
                          docstring exists to prevent. No new logging.
Testing Notes:            Happy path: an XML string with nested elements and attributes
                          renders with tag/attribute-name/attribute-value coloring, not
                          JSON's key/string/number/boolean coloring. Security regression
                          (the highest-value test here, given the file's own documented
                          threat model): an XML string containing a literal
                          `</span><script>alert(1)</script>` as element text content or an
                          attribute value must render as inert, escaped text — not execute
                          — mirroring whatever regression coverage (existing or new)
                          protects `highlightJson` against the same class of input. `format`
                          omitted/`"json"` → output identical to today's `highlightJson`
                          path (regression, NFR2-equivalent for the frontend).
```

```
Task ID:                  P4.A-04
Title:                    DataPreviewPage passes endpoint.response_format to RawResponseViewer
Description:              In `frontend/src/features/data-preview/pages/DataPreviewPage.tsx`,
                          change the `RawResponseViewer` call (currently
                          `<RawResponseViewer body={preview.data.raw_response_body} />`,
                          line 197) to also pass `format={endpoint?.response_format}` — the
                          `endpoint` object is already fetched on this page via
                          `useEndpoint(profileId, endpointId)` (line 26-29) for the
                          breadcrumb/header, so no new data fetch is needed.
Why This Matters:         P4.A-03 gives `RawResponseViewer` the ability to render XML
                          correctly, but the only call site that renders live preview data
                          (`DataPreviewPage`) doesn't yet tell it which format to use —
                          without this task, every endpoint (XML included) would still hit
                          the JSON-highlighting default.
Dependencies:             P4.A-01, P4.A-03
Inputs/Preconditions:     `DataPreviewPage.tsx`'s existing `useEndpoint` call and
                          `RawResponseViewer` import (confirmed, lines 10,26-29,197).
Output/Artifact:          `RawResponseViewer` receives the correct `format` for the
                          endpoint currently being previewed; verifiable by toggling "Raw
                          Response" on an XML-configured endpoint's preview and observing
                          XML-highlighted output, and on a JSON-configured endpoint's
                          preview observing unchanged JSON-highlighted output.
Placeholders:             None
Decision Type:            None — pure prop-threading, no design choice.
Security & Observability: N/A — no new data surface; `endpoint.response_format` is already
                          fetched, non-secret configuration.
Testing Notes:            Manual (per P4.A-02's note on this codebase's thin frontend
                          coverage): fetch a preview for an XML-configured endpoint, toggle
                          "Raw Response", confirm XML rendering; repeat for a JSON-configured
                          endpoint, confirm no visual change from before this phase.
```

### P4.B — End-to-End Validation  [REVIEW-GATE]

**Objective**: Prove the complete, already-integrated pipeline (connection test → configure `data_root_path`/pagination → schema inference → data preview, entirely through the UI built in P4.A) against a real, namespaced public XML API, per SC8 — closing out the one thing no prior phase has actually done: exercise this feature against a live external XML server rather than fixtures/`httpx_mock`.
**Deliverables**: A completed, documented walkthrough; a new section in `docs/e2e-testing-guide.md` following the existing section pattern.
**Complexity/risk**: High reproducibility risk, low design complexity — gated (per `plan.md` §8) because it depends on a real, uncontrolled external server (availability, response shape drift, rate limits) rather than because the work itself is architecturally hard. OD-1 must be resolved before P4.B-01 starts.

```
Task ID:                  P4.B-01
Title:                    Execute the full connection-test → configure → infer → preview flow against the DNB SRU API
Description:              Using the running app's UI (per `docs/e2e-testing-guide.md`'s
                          existing walkthrough style, e.g. §2 "No Auth — JSONPlaceholder"):
                          (1) create a `ConnectionProfile` with `Auth Type: No Auth`, `Base
                          URL: https://services.dnb.de/sru/dnb`; (2) run **Test Connection**
                          and confirm `Detected Format: xml`; (3) create an `Endpoint` against
                          the DNB SRU search operation (standard SRU GET params:
                          `operation=searchRetrieve`, `version`, `query`, `recordSchema=oai_dc`,
                          per the confirmed real sample's own `<recordSchema>oai_dc</recordSchema>`
                          — construct the exact `query=`/`version` values per DNB's public SRU
                          documentation, since Phase 1's spike did not preserve its literal
                          request URL) — confirm `response_format` defaults to `xml` per
                          P4.A-02, editable; (4) configure pagination per OD-1(a):
                          `Strategy: Cursor`, `cursor_request_param: startRecord`,
                          `cursor_response_path: searchRetrieveResponse.nextRecordPosition`;
                          set `Data Root Path: searchRetrieveResponse.records.record` and
                          `Record Count Path: searchRetrieveResponse.numberOfRecords` (both
                          already proven against this exact real data by
                          `test_schema_inference.py:37`'s `XML_DATA_ROOT_PATH`); (5) run
                          **Schema Inference** and confirm a sane, editable field list
                          appears (expect `dc.creator`-style paths, matching the DNB
                          Dublin-Core shape Phase 1 already characterized); (6) run **Data
                          Preview**, confirm the table renders rows/columns correctly, and
                          toggle **Raw Response** to confirm it shows real XML text via
                          P4.A-03's new branch, not a JSON reinterpretation. Record the
                          actual result of every step (pass/fail, any deviation from
                          expectation) — this record is P4.B-02's source material.
Why This Matters:         SC8 explicitly requires this: "End-to-end validation against a
                          real SRU (or comparably namespaced) public XML API completes the
                          full flow ... without manual workarounds." Every prior phase
                          validated against fixtures or `httpx_mock` — this is the first and
                          only point in the pipeline that proves the feature against a real
                          server a real target user would actually configure.
Dependencies:             P4.A-01, P4.A-02, P4.A-03, P4.A-04 (needs the UI built in this
                          phase to drive the flow); OD-1 resolved (target/strategy choice)
Inputs/Preconditions:     Running backend + frontend (`docs/project-detail.md` §3 local-run
                          commands); network access to `services.dnb.de` (confirmed
                          reachable — Phase 1's spike already fetched real data from it);
                          no credentials needed (No Auth).
Output/Artifact:          A recorded, step-by-step pass/fail account of the full flow
                          against the real DNB SRU API — the direct input to P4.B-02;
                          verifiable by the human re-running the same steps against the
                          same live endpoint and observing the same outcome (allowing for
                          the target catalog's own data changing over time, which does not
                          invalidate the validation).
Placeholders:             None
Decision Type:            None — executes per OD-1's resolved option; no further design
                          choice at this task's level.
Security & Observability: No credentials involved (No Auth). This step calls a real,
                          third-party government service — keep request volume to what
                          manual validation actually requires (a handful of requests), not
                          a stress test; respect DNB's own SRU usage terms. Do not commit
                          any full raw response body containing more than what's needed for
                          the guide's illustrative snippets (matches the existing guide's
                          own convention of small, truncated example payloads, e.g. §7.3's
                          `tracks` snippet).
Testing Notes:            This task IS the manual test (no separate automated coverage is
                          possible against a live external server by design). Happy path:
                          all 6 numbered steps above succeed. Edge cases to specifically
                          confirm, not just assume: cursor pagination actually advances
                          across at least 2 pages before stopping (proves `CursorStrategy`
                          against real XML, not just the mocked fixture Phase 3 already
                          covered); the DEV-1 `_next_url` bug is not encountered (expected,
                          since Cursor strategy never touches that code path — confirm this
                          holds, don't just assume it from OD-1's reasoning); Raw Response
                          for this endpoint shows text starting with `<?xml` or the
                          `<searchRetrieveResponse` root tag, not `{`.
```

```
Task ID:                  P4.B-02
Title:                    Document the DNB SRU validation as a new section in docs/e2e-testing-guide.md
Description:              Add a new numbered top-level section to
                          `docs/e2e-testing-guide.md` (after the existing §8 OAuth AC
                          section, renumbering §9-11 and the two trailing Quick Reference
                          tables accordingly, or appending after §11 as an unnumbered final
                          section if renumbering the whole file is judged too invasive —
                          implementor's call, note whichever is chosen), titled something
                          like "XML Responses — Deutsche Nationalbibliothek SRU", following
                          the exact structure every existing section already uses ("Profile
                          Setup → Connection Test → Endpoint Creation → Pagination →
                          Schema", per the guide's own "How to Read This Guide" convention,
                          line 9-13). Populate it from P4.B-01's actual recorded results —
                          not a hypothetical walkthrough — including the real field values
                          used (base URL, `data_root_path`, `record_count_path`, cursor
                          strategy params) and the actual `Detected Format`/schema-inference
                          outcome observed. Do not add a new row to the existing "Quick
                          Reference: All Supported Auth Types" or "All Pagination
                          Strategies" tables — this doesn't introduce a new auth type or
                          pagination strategy, so those tables are correctly left untouched
                          (no drive-by edits).
Why This Matters:         `plan.md`'s stated Phase 4 artifact is "an e2e validation note
                          (addendum to or new section in `docs/e2e-testing-guide.md`)" —
                          without this, P4.B-01's validation is a one-time, unrecorded
                          manual act that the next person configuring an XML endpoint
                          cannot learn from, breaking the guide's own stated purpose as a
                          complete walkthrough reference. Matching every other auth-type/
                          pagination-strategy section already in this guide gives a future
                          user configuring their own SRU/XML endpoint a concrete worked
                          example, not just a pass/fail note buried in a phase report.
Dependencies:             P4.B-01
Inputs/Preconditions:     P4.B-01's recorded results; `docs/e2e-testing-guide.md`'s current
                          structure (confirmed, 970 lines, sections 1-11 plus 2 trailing
                          Quick Reference tables).
Output/Artifact:          A new, complete section in `docs/e2e-testing-guide.md` documenting
                          the validated XML flow; verifiable by a human following the new
                          section's steps verbatim and reproducing P4.B-01's outcome.
Placeholders:             None
Decision Type:            None — documentation only.
Security & Observability: N/A — documentation, no runtime code.
Testing Notes:            N/A (documentation task) — the "test" is P4.B-01 itself; this
                          task's own correctness check is a human proofread confirming the
                          documented steps match what was actually done and observed.
```

---

## 4. Phase Acceptance Criteria & Verification

**Completion criteria** (falsifiable, traced to `requirement.md` §5 Success Criteria this phase owns or closes out):

- **AC1** (traces SC1, UI half — backend half already MET in Phase 2): WHEN a user creates an `Endpoint` through the endpoint form, THE SYSTEM SHALL show `response_format` pre-populated from the parent profile's last detected format and SHALL let the user change it before or after creation.
- **AC2** (traces SC6, UI half — backend half already MET in Phase 3): WHEN a user opens the Raw Response panel for an XML-configured endpoint's data preview, THE SYSTEM SHALL render the original XML text with XML-appropriate syntax highlighting, not a JSON reinterpretation or JSON-shaped coloring.
- **AC3** (traces SC2-SC5, SC7, via live validation rather than fixtures): WHEN the full flow (connection test → configure → infer → preview) is run through the UI against the real DNB SRU API, THE SYSTEM SHALL complete every step without manual workarounds, errors, or backend exceptions.
- **AC4** (traces SC8 directly): The DNB SRU end-to-end validation is executed and its outcome is documented in `docs/e2e-testing-guide.md` per the existing section pattern.
- **AC5** (regression, NFR2): Existing JSON-configured endpoints' form behavior and Raw Response rendering are visually and functionally unchanged from before this phase.
- **AC6** (`plan.md` §11 "Final check"): At phase completion, `requirement.md` §5's SC1-SC8 are walked one by one against the now-complete feature and confirmed to hold — SC1-SC5/SC7 already confirmed by Phases 2-3's own test suites and reconciliations; SC6 confirmed by AC2/P4.A-03; SC8 confirmed by AC4/P4.B.

**Manual verification steps** (human smoke test):

1. Create an endpoint under a profile whose last connection test detected `json` — confirm the form's `response_format` Select shows "JSON" by default and can be changed.
2. Create an endpoint under a profile whose last connection test detected `xml` (e.g. after testing against `services.dnb.de/sru/dnb`) — confirm the Select shows "XML" by default.
3. Edit an existing endpoint and change `response_format` — confirm the change persists on reload.
4. Open Data Preview for an XML-configured endpoint, toggle Raw Response — confirm real XML text renders with XML highlighting, starting with `<?xml` or the document's root tag, not `{`.
5. Open Data Preview for an existing JSON-configured endpoint — confirm Raw Response is unchanged (still JSON-highlighted).
6. Execute P4.B-01's full walkthrough against the live DNB SRU API end to end.

**Expected automated coverage** (described, not scripted):

- `frontend/src/shared/types/domain.test.ts`: one new `expectTypeOf` assertion confirming `Endpoint["response_format"]` is the literal union `"json" | "xml"`.
- `npm run typecheck --prefix frontend`: passes with zero new errors across every file touched (`domain.ts`, `endpointApi.ts`, `endpointSchema.ts`, `EndpointFormPage.tsx`, `RawResponseViewer.tsx`, `DataPreviewPage.tsx`).
- `npm run lint --prefix frontend` / `npm test --prefix frontend` (`vitest run`): pass with zero regressions to the 3 pre-existing test files.
- No backend code changes this phase — the full backend suite (475 passed as of Phase 3's reconciliation) is not expected to change and is not part of this phase's own artifact set.
- P4.B-01 itself is the end-to-end coverage SC8 requires; by design it cannot be automated (real external server).

---

## 5. Handoff Note

Build against commit `78d2d79e839d43124c77d304202299bb144393b4` on branch `001-xml-response-support`. The one `[REVIEW-GATE]` is subphase P4.B (external network dependency, not fully reproducible/deterministic). No `[IRREVERSIBLE]` tasks this phase. One Open Decision (OD-1, the e2e target/strategy choice) must be confirmed before P4.B-01 is executed — the tasks as written assume option (a) (DNB SRU + `CursorStrategy`); if the human prefers option (b) or (c), P4.B-01/02 need to be revised accordingly, and choosing (b) also requires inserting a preliminary DEV-1 bug-fix task before P4.B-01. The implementor writes the code/tests/documentation and commits **nothing** — the human commits.

This is the final phase of `001-xml-response-support`. Once P4.A/P4.B are implemented, reviewed, and reconciled, the feature is complete: re-run `requirement.md` §5's SC1-SC8 one last time against the finished feature (AC6 above) before considering the feature closed out.
