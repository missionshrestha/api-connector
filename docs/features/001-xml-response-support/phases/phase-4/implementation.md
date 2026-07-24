Feature `001-xml-response-support` · Phase 4 — Frontend & End-to-End Validation
Baseline commit: `78d2d79e839d43124c77d304202299bb144393b4` on branch `001-xml-response-support`
State: UNCOMMITTED working tree (review with: `git diff 78d2d79e839d43124c77d304202299bb144393b4`)
Status: READY FOR REVIEW. Both subphases complete: P4.A (UI Surfacing) and P4.B (End-to-End Validation, resolved past its `[REVIEW-GATE]` halt — see §11). This is the final phase of `001-xml-response-support`.

---

## 1. Summary

P4.A (UI Surfacing) is fully implemented and verified: `response_format` now flows end-to-end through the frontend — hand-mirrored types, the endpoint form's new Select control (with the same create-mode server-side-fallback default the backend already applies), and a new XML-aware branch in `RawResponseViewer` so an XML-configured endpoint's raw response renders with XML syntax highlighting instead of being force-fit through the JSON highlighter.

P4.B (End-to-End Validation) initially halted at its `[REVIEW-GATE]` because its gating Open Decision (OD-1) was unresolved and I had no browser-automation tooling to drive the actual UI. The human resolved this by confirming OD-1's recommended option and asking me to execute the validation myself and research what was needed. Since I still had no browser tooling, I drove the exact same backend code paths a UI walkthrough would (`ConnectionTestService`, `PaginationEngine`, `SchemaInferenceEngine`, `DataPreviewService`) via direct REST calls against the running app, using the real, live DNB SRU API — this is a tactical substitution for "through the UI," recorded as a `[local]` deviation in §5. The frontend-only claims this can't reach (the Select's rendering, `RawResponseViewer`'s highlighting) are separately verified: the Select was already code-traced in P4.A, and `highlightXml` was additionally run directly against the real captured DNB response body (not just synthetic test fixtures) to confirm it holds up on genuine namespaced data.

All 6 of P4.B-01's numbered steps completed successfully against the live DNB target once the correct configuration was found; the full flow ran without errors, exceptions, or hacks — only standard, supported configuration fields.

After this initial resolution, the human asked for `e2e-testing-guide-xml.md` to additionally cover "various cases, urls... search various xml based api responses" — read as wanting the same breadth `e2e-testing-guide.md` has (one section per real API) applied to XML, not just the single DNB walkthrough. I researched and validated **5 more real, live, independently-operated XML APIs** beyond DNB — World Bank (Page/Size), NCBI E-utilities/PubMed (Offset/Limit), USGS Earthquakes (Atom/GeoRSS, No Pagination), BBC News RSS (RSS 2.0 + CDATA, No Pagination), and a public NOAA S3 bucket (Cursor via opaque continuation-token) — each run through the same real backend pipeline as DNB, chosen specifically to cover every pagination strategy meaningful for a real XML source and several genuinely different XML shapes.

This broader sweep surfaced **three genuine, previously-unknown findings**, none of them bugs in `001-xml-response-support` itself:
1. **The DNB base-URL/path gotcha** (single-fixed-endpoint APIs rejecting any appended path character, colliding with `Endpoint.path` always being non-empty) — now confirmed to recur, in a milder form, across 4 of the 6 APIs tested (a bare `base_url` root often doesn't reflect the actual endpoint's format or reachability at all).
2. **World Bank's root-level pagination metadata is expressed as XML attributes** (`<wb:countries page="1" pages="59" total="295">`), and this app's dot-notation path validator (`^[\w]+(\.[\w]+)*$`) structurally rejects any `@`-prefixed segment — confirmed via a real `400` validation error attempting `record_count_path="countries.@total"`. Record-level attribute fields are unaffected; only root-level pagination/count metadata expressed as an attribute is unreachable.
3. **NCBI's `esearch` endpoint returns a list of bare scalar strings** (not objects) at its natural `data_root_path` — Schema Inference silently returns zero fields (not an error), which then blocks Data Preview with a `422` that doesn't point back at the real cause.

All three are format-agnostic (would affect equivalent JSON APIs identically) and are documented, not fixed, per Rule 2/6 (out of this feature's scope). `docs/e2e-testing-guide-xml.md` (rewritten, now 6 full per-API sections mirroring `e2e-testing-guide.md`'s structure exactly, plus a limitations section, XSS section, and quick reference) documents all of this, as a standalone companion file per the human's explicit request rather than a new section within the existing guide (a deliberate deviation from the breakdown's originally-specified delivery mechanism — see §5).

## 2. What Changed — file by file

**P4.A (frontend code):**
- `frontend/src/shared/types/domain.ts`: added `export type ResponseFormat = "json" | "xml"`, and `response_format: ResponseFormat` to the `Endpoint` interface, positioned to match `EndpointReadSerializer.Meta.fields`'s field order.
- `frontend/src/shared/types/domain.test.ts`: one new `expectTypeOf` assertion for the literal union.
- `frontend/src/features/endpoint/api/endpointApi.ts`: `response_format?: ResponseFormat` added to `EndpointCreateRequest`.
- `frontend/src/features/endpoint/schemas/endpointSchema.ts`: `response_format: z.enum(["json", "xml"])` added to the form's zod object.
- `frontend/src/features/endpoint/pages/EndpointFormPage.tsx`: new `Response Format` Select, create-mode default from `useProfile(profileId).last_test_detected_format` (mirrors `views/endpoint.py:116-120`'s fallback exactly), edit-mode `reset()` seeding, manual-override handling via `setValue(..., { shouldDirty: true })`.
- `frontend/src/features/data-preview/components/RawResponseViewer.tsx`: new `format?: ResponseFormat | undefined` prop (default `"json"`), new `highlightXml()` function, branch on `format`.
- `frontend/src/features/data-preview/pages/DataPreviewPage.tsx`: passes `format={endpoint?.response_format}` to `RawResponseViewer`.
- `frontend/src/features/data-preview/components/__tests__/RawResponseViewer.dom.test.tsx` (new): 4 tests — XML coloring happy path, JSON-path regression, 2 XSS-prevention regression tests.

**P4.B (documentation only — no product code):**
- `docs/e2e-testing-guide-xml.md` (new file): mirrors `e2e-testing-guide.md`'s per-API section structure exactly (Profile Setup → Connection Test → Endpoint Creation → Pagination → Schema). 6 full sections, one per real, live, independently-operated XML API — Deutsche Nationalbibliothek SRU (Cursor, integer position), World Bank (Page/Size), NCBI E-utilities/PubMed (Offset/Limit), USGS Earthquakes (Atom/GeoRSS, No Pagination), BBC News RSS (RSS 2.0 + CDATA, No Pagination), NOAA GOES-16 S3 bucket (Cursor, opaque token) — plus a consolidated Known Limitations section (the 3 findings in §1), an XSS-safety section, and a quick-reference table. Per the human's two explicit requests: first for "various cases," then for breadth across "various xml based api responses" with real URLs, "similar to that of json."
- `docs/e2e-testing-guide.md`: one-line pointer added at the top (below the title) to the new companion guide — no restructuring, no renumbering of existing sections (the breakdown itself flagged in-place renumbering as possibly "too invasive").
- `docs/features/001-xml-response-support/phases/phase-4/implementation.md` (this file) and `docs/features/001-xml-response-support/decisions.md`: this phase's record.
- `docs/_meta/active-context.md`: phase status field updated.

No backend product code was touched this phase (P4.A is frontend-only; P4.B's live validation used the existing, unmodified backend against real data — zero backend files changed).

## 3. How It Works

**P4.A** — unchanged from the pre-resolution record; see §3 of the original halt-time writeup, preserved here: `EndpointFormPage`'s create-mode `useEffect` mirrors the server's `response_format` fallback so the Select shows the soon-to-be-actual default before submit; a user's manual selection (`shouldDirty: true`) permanently wins. `DataPreviewPage` threads `endpoint?.response_format` into `RawResponseViewer`, which branches between the pre-existing `highlightJson` and the new `highlightXml` — both escape first, color second, over already-inert text.

**P4.B** — the validation flow, run via direct REST calls against the app's existing, unmodified API (no product code path differs from what a UI click would trigger):
1. **Format-detection profile** (`ConnectionProfile` #14, `base_url=https://services.dnb.de/sru/dnb`): `Test Connection` → all 6 diagnostic steps pass, `format_detection` reports `"xml"` against a real SRU `explainResponse`. Proves SC1's auto-detection claim against a live external server.
2. **Discovered the base-URL/path gotcha** (Case 2): reproduced through the app itself — an `Endpoint` with `path="/"` under profile #14 fails schema inference with a misleading `422 API_CONN_051` ("no records... verify data_root_path"), when the real cause is DNB returning a well-formed `<diagnostics>` XML document (not a transport error) because *any* character after `/sru/dnb` breaks its routing. Confirmed via raw `curl` first, then reproduced and then cleaned up (deleted) through the app to get the exact in-app symptom for the record.
3. **Working profile** (`ConnectionProfile` #15, `base_url=https://services.dnb.de`) + **Endpoint** (#23, `path=/sru/dnb`, `response_format` manually set to `"xml"` since this profile's own connection test 404s at the bare host and never reaches format detection — exercising the manual-override half of AC1/SC1 that profile #14's clean auto-detect path doesn't reach).
4. **Cursor pagination** configured (`cursor_request_param=startRecord`, `cursor_response_path=searchRetrieveResponse.nextRecordPosition`). Confirmed advancing across real pages twice: directly via `curl` (page 1 → `nextRecordPosition=4`; `startRecord=4` → `nextRecordPosition=7`) and through the app (schema inference sampled 9 records = 3 real pages × 3 records/page, inferred from each field's `null_percentage` denominator).
5. **Schema Inference** ran against the live endpoint, producing 16 fields with zero namespace-prefix leakage (`recordData.dc.creator`, not a Clark-notation URI), correct list-coercion for `dc:creator`/`dc:identifier`, and correct attribute/text convention (`@type`/`#text`) — matching Phase 1's spike findings exactly, now reconfirmed against fresh live data rather than the frozen sample.
6. **Data Preview** (`row_limit=5`) returned 5 correctly-shaped rows, `has_more: true`, and `raw_response_body` starting with `<?xml version="1.0" encoding="UTF-8"?>` — confirmed DEC-6 holds against real data.
7. **`highlightXml` re-verified against the real captured response body** (not just the component test's synthetic strings): correct tag/attribute coloring, `<?xml ...?>` declaration falls through unhighlighted as designed, no live `<script>` element producible.

8. **Extended to 5 more real APIs** after the human's follow-up request for breadth "similar to that of json": World Bank (Page/Size — `page`/`per_page` params, `total_pages_path` omitted since its total lives in an unreachable root `@attr`, falls back to record-count comparison, confirmed advancing 3 pages via 12 records fetched at `page_size=5`); NCBI E-utilities `esearch` (Offset/Limit — `retstart`/`retmax`, confirmed stateless via direct `curl`; Schema Inference returned 0 fields since `IdList.Id` resolves to bare scalars, not objects — a new, distinct finding from Case 2's); USGS Earthquakes (No Pagination, Atom/GeoRSS, 13 fields including attribute-only `link.@href`); BBC News RSS (No Pagination, RSS 2.0 — confirmed CDATA-wrapped `title`/`description` unwrap to clean strings against a real feed, not just Phase 1's synthetic sample); NOAA GOES-16 S3 bucket (Cursor via opaque `continuation-token`/`NextContinuationToken` — confirmed advancing 3 pages via 12 objects fetched at `max-keys=5`; notably the only one of the 6 whose bare `base_url` root *does* auto-detect `xml` correctly, contrasting with the recurring host-root mismatch seen in the other 5).

`docs/e2e-testing-guide-xml.md` records all 6 APIs as 6 full sections mirroring `e2e-testing-guide.md`'s own structure, following its style (tables for config fields, `>` blockquotes for gotchas), plus a consolidated Known Limitations section (§8 of that file) covering all 3 findings, as a standalone file per the human's explicit request.

## 4. Decisions Made

*(P4.A decisions, unchanged from the pre-resolution record:)*
- **`highlightXml` uses a per-tag callback with attribute-pass-before-tag-name-pass**, not `highlightJson`'s sequential whole-string `.replace()` chain — found and avoided a real, pre-existing bug in the untouched `highlightJson` (its number-coloring regex re-matches digit sequences inside its own injected `class="text-blue-600..."` markup). Not fixed in `highlightJson` itself (out of scope, Rule 2/6); flagged in §9.
- **Tag-matching regex only recognizes tags starting with a letter after `&lt;`/`&lt;/`**, so declarations/comments/CDATA fall through as plain, still-escaped text — the task's own allowed "non-over-engineered fallback."
- **Known, accepted cosmetic edge case**: an attribute value containing a literal `>` can cause the non-greedy tag regex to terminate early; never a security issue (escaping runs unconditionally first), only affects coloring correctness on already-inert text.

*(P4.B decisions, this resolution:)*
- **OD-1 resolved as recommended: DNB SRU + `CursorStrategy`**, per the human's explicit instruction to proceed with what was recommended. The breakdown's own reasoning (avoids the unfixed `_next_url` bug structurally, not by luck; reuses already-proven paths from Phases 1/3) held up on inspection — confirmed independently via Case 4's direct verification that `CursorStrategy.next_params()` never produces the `_next_url` sentinel.
- **P4.B-01 executed via direct backend REST calls, not a browser UI.** No browser-automation tooling was available in this session (confirmed via the deferred-tools listing, same as at the original halt). The human's instruction ("research yourself and do what's recommended") was read as authorizing this substitution rather than requiring me to wait for a human to click through the UI — it exercises the identical backend code paths a UI action would trigger, and P4.A's frontend-only pieces (the Select, `highlightXml`) are separately verified (code-tracing in P4.A; `highlightXml` re-run directly against the real captured response body in this resolution). Recorded as `[local]` in §5 — a tactical substitution within the task's stated intent (Rule 6), not a scope change to what was validated.
- **Two `ConnectionProfile`s used instead of one**, once Case 2's gotcha was found: profile #14 (`base_url` = the exact SRU endpoint) demonstrates clean format auto-detection (Case 1); profile #15 (`base_url` = host root, `Endpoint.path` = `/sru/dnb`) is the one actually used for pagination/schema/preview, since that's the only split that produces working requests. This mirrors a real fork a human following the breakdown's literal "Base URL: https://services.dnb.de/sru/dnb" instruction would hit, so both are preserved and documented rather than silently using only the working one and hiding the discovery.
- **`docs/e2e-testing-guide-xml.md` as a new, separate file** rather than a new section inside `docs/e2e-testing-guide.md`, per the human's explicit request ("I also want e2e-testing-guide-xml.md with various cases"). This supersedes the breakdown's original P4.B-02 delivery mechanism (a new section in the existing file, with in-place renumbering or an unnumbered trailing section). A one-line pointer was added to the existing guide for discoverability, since Rule 2 favors the smallest surface but total invisibility of the new guide from the existing one seemed like the wrong trade-off. Weighed against the Decision Priority Order: the human's explicit, current instruction is the most direct signal of Business Value here and overrides the breakdown's own tentative mechanism (which itself only weakly committed to in-place editing, flagging renumbering as "possibly too invasive").
- **Extended to 6 real APIs total, one section each, mirroring `e2e-testing-guide.md`'s exact per-API structure**, after the human's second follow-up: *"I also want e2e-testing-guide-xml.md with various cases, urls, similar to that of json, search various xml based api responses."* Read as: the JSON guide's breadth (one section per API, covering different auth/pagination combinations) is the target shape, not just a single DNB walkthrough with narrative "cases." I researched and validated 5 more real, live, unauthenticated XML sources directly (`curl` first to confirm exact request/response shape, then configured and ran each through the app itself — Rule 1: verify, don't assert), chosen to cover every pagination strategy meaningful against a real XML source (Cursor ×2 flavors, Offset/Limit, Page/Size, No Pagination ×2) and several genuinely different XML shapes (namespaced library metadata, Atom/GeoRSS, RSS+CDATA, AWS's S3 format) rather than 5 more SRU-shaped near-duplicates of DNB. `NextURL`/`LinkHeader` were deliberately not force-fit into an XML example — forcing one would risk hitting DEV-1 for no real benefit, and both are already covered for JSON in the main guide; noted explicitly in the new guide's §8/§10 rather than silently omitted.
- **World Bank's `total_pages_path` left blank rather than worked around** — its total-pages value lives in a root-level XML attribute (`@pages`) the dot-notation validator can't express (see the finding below). Rather than inventing a workaround (e.g., a separate lookup call this app doesn't support), left it blank and let `PageSizeStrategy`'s existing, documented fallback (compare each page's record count to `page_size`) handle termination — confirmed working via a 12-record, 3-page fetch. This is the correct behavior already built into the strategy for exactly this situation (an optional field), not a gap I had to route around.

## 5. Deviations from the Breakdown

- **[local] P4.B-01 executed via direct backend API calls instead of the running app's browser UI.** The breakdown's own words: this task "IS the manual test," implying UI interaction. No browser-automation tooling was available. Same backend code paths exercised either way; frontend-only pieces separately verified (see §4). If a higher-fidelity, literal browser click-through is wanted, it can be layered on top later without invalidating anything recorded here — the backend behavior this validates won't change.
- **[local] Two `ConnectionProfile`s used for DNB, not one**, once the base-URL/path gotcha was found mid-validation — see §4.
- **[local] `docs/e2e-testing-guide-xml.md` is a new file, not a new section in `docs/e2e-testing-guide.md`** — direct human request, supersedes the breakdown's tentative mechanism. See §4.
- **[local] Validated 5 additional real APIs beyond DNB**, per the human's explicit follow-up request for breadth. Expands the guide's scope beyond the breakdown's single-target P4.B-01/02 spec, but stays within the same task's intent (prove the pipeline against real external XML) — recorded as `[local]`, not `[contract]`, since it changes documentation breadth only, not any product code or contract.
- **[local]** (carried from the pre-resolution record) one whitespace cleanup adjacent to the new `useEffect` in `EndpointFormPage.tsx`.
- No `[contract]` or `[plan]` deviations. `breakdown.md` was not edited.

## 6. Contract Changes — for the Reconciler

None. P4.A is purely additive frontend surface over an already-shipped backend contract. P4.B added no product code at all — documentation only, plus 7 new `ConnectionProfile` rows (DNB ×2, World Bank, NCBI, USGS, BBC, NOAA S3), 6 `Endpoint` rows, 5 `PaginationConfig` rows, and ~60 `SchemaField` rows across all endpoints in the local dev database (real data, not fixtures — created via the running app's own API, same as any real user's data; not part of the deployable artifact). Two findings (the `@attr` path-validator rejection for World Bank, and the empty-schema result for NCBI) are themselves *evidence of existing validator/inference behavior*, not new behavior — no code was changed to produce them.

## 7. Tests & Verification

**Frontend CI gates** (`docs/project-detail.md` §3 exact commands, `nvm use 22`):

```
$ npm run typecheck --prefix frontend   → zero errors
$ npm run lint --prefix frontend        → zero warnings
$ npm test --prefix frontend            → Test Files 4 passed (4), Tests 20 passed (20)
```

All 3 pre-existing test files pass unmodified (`domain.test.ts` +1 assertion). New `RawResponseViewer.dom.test.tsx` (4 tests) covers XML coloring, JSON-path regression, and 2 XSS-prevention regressions — see the original §7 record (unchanged by this resolution).

**P4.B — live validation against 6 real XML APIs, run 2026-07-24. Full narrative and exact request/response evidence for all 6 in `docs/e2e-testing-guide-xml.md`.**

*Deutsche Nationalbibliothek SRU* (`https://services.dnb.de/sru/dnb`, profiles #14/#15, endpoint #23, Cursor):

| Step | Result |
|---|---|
| Connection Test (profile #14, exact SRU endpoint) | `overall_passed: true`, `format_detection: "xml"` (`content_type_header`), 27,851-byte sample captured |
| Connection Test (profile #15, host root — for the working endpoint split) | `overall_passed: false` (404 at bare host, expected and documented) |
| Endpoint creation (#23, `path=/sru/dnb`, `response_format=xml` manual) | Created successfully |
| Schema Inference | 16 fields, 0 namespace leakage, correct list/attribute coercion; 9 records sampled = confirmed 3-page cursor advance |
| Data Preview (`row_limit=5`) | 5 rows, `has_more: true`, `raw_response_body` starts with `<?xml version="1.0" encoding="UTF-8"?>` |
| `highlightXml` vs. real captured response body | Correct tag/attribute coloring, no live `<script>` producible |
| DEV-1 (`_next_url` bug) encountered? | No — confirmed by code inspection and by observing every page's query params intact throughout |

*The other 5* (profiles #16-#20, endpoints #25-#29):

| API | Pagination | Connection Test | Schema Inference | Data Preview | Finding |
|---|---|---|---|---|---|
| World Bank | Page/Size (`total_pages_path` omitted) | `overall_passed: false` (404 at host root) | 18 fields incl. record-level `@id`/`@iso2code` attributes | 12 rows fetched = 3-page advance via record-count fallback; raw body has a literal BOM before `<?xml` | `record_count_path="countries.@total"` rejected: `400`, dot-notation validator disallows `@` |
| NCBI E-utilities (`esearch`) | Offset/Limit (`retstart`/`retmax`) | `overall_passed: true` but `format_detection: "html"` (301 redirect at root) | **0 fields** (`HTTP 200`, not an error) | `422` — "no fields marked for inclusion" | `IdList.Id` resolves to bare scalar strings; `_walk_record` has nothing to flatten. Also: real external-DTD `<!DOCTYPE>` parsed safely (SC7 live confirmation) |
| USGS Earthquakes | No Pagination | `overall_passed: true` but `format_detection: "html"` (root is the website homepage) | 13 fields incl. attribute-only `link.@href`/`@rel`/`@type` (no `#text`) | 3 rows, raw body starts `<?xml ...?><feed xmlns="...Atom"...` | none beyond the recurring host-root mismatch |
| BBC News RSS | No Pagination | `overall_passed: false` (404 at host root) | 9 fields; `title`/`description` (CDATA-wrapped in source) resolve to clean unwrapped strings | 3 rows, `rows[0].title` matched the live top headline at capture time | first confirmation of CDATA handling against a real (not synthetic) feed |
| NOAA GOES-16 S3 | Cursor (opaque `continuation-token`) | `overall_passed: true`, `format_detection: "xml"` **even at bare root** | 7 fields, uniform shape, `LastModified` correctly inferred `datetime` | 12 objects fetched = 3-page advance via opaque token | the one profile whose host root *does* auto-detect correctly — contrast case for the recurring-mismatch pattern |

Full narrative and exact request/response evidence for all 6 APIs, including the 3 findings' precise reproduction steps, are in `docs/e2e-testing-guide-xml.md`.

**Security Self-Check** (Rule 3, extending the original P4.A check):
- **XSS (CWE-79)**: re-verified `highlightXml` against real, unmodified DNB response text (not just synthetic fixtures) — no live `<script>` element producible. Original 2 automated regression tests still cover the documented threat model directly.
- **SSRF (CWE-918)**: P4.B's outbound calls (across all 6 APIs) all went through the existing, unmodified `BaseHTTPClient`/`ConnectionTestService`/`PaginationEngine` code paths — no new outbound-request code was written. `SSRF_PROTECTION_ENABLED=False` in this local dev environment (confirmed via `.env`, value only — not a secret), matching the documented "fine for private/trusted deployments" posture; not a new exposure introduced by this phase.
- **No secrets involved**: all 6 targets are unauthenticated (No Auth); no credentials were created, viewed, or logged during this validation.
- **Dependencies**: none added this phase (P4.A or P4.B).
- **No secrets appear anywhere in this record, the diff, or `docs/e2e-testing-guide-xml.md`** (the guide's illustrative excerpts are all public government/library/news data, matching the existing guide's own convention for small snippets).

## 8. Phase Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| AC1 | Endpoint form shows `response_format` pre-populated from the parent profile's last detected format, user-editable | **Met** | P4.A code trace + auto-detect (DNB profile #14, S3 profile #20) and manual-override (the other 5 profiles) paths both exercised live. |
| AC2 | Raw Response panel renders XML text with XML-appropriate highlighting for XML-configured endpoints | **Met** | `RawResponseViewer.dom.test.tsx` (automated) + `highlightXml` re-verified against real captured DNB data. |
| AC3 | Full flow (connection test → configure → infer → preview) completes via UI against a real, namespaced XML API | **Met, with a noted substitution** | Full flow completed with zero errors/exceptions against 5 of 6 real targets using correct, supported configuration (DNB, World Bank, USGS, BBC, NOAA S3 — all reached Data Preview successfully); NCBI reached Schema Inference cleanly but hit the scalar-record finding before Preview, which is itself a legitimate, informative validation outcome, not a flow failure — driven via direct backend API calls, not a browser UI, per §4/§5's recorded deviation. |
| AC4 | XML validation executed and documented, covering various cases/APIs | **Met, with a noted substitution** | Documented in the new, separate `docs/e2e-testing-guide-xml.md` (human's explicit request, twice) rather than a section within `docs/e2e-testing-guide.md` — a one-line pointer added to the latter for discoverability. See §4/§5. |
| AC5 | Existing JSON-configured endpoints' form behavior and Raw Response rendering unchanged | **Met** | `RawResponseViewer.dom.test.tsx` byte-for-byte `innerHTML` equality test; zero other `RawResponseViewer` call sites exist (grepped). |
| AC6 | `requirement.md` §5 SC1-SC8 all confirmed at phase completion | **Met** | SC1/SC2/SC4/SC6/SC8: newly reconfirmed live this phase, now against 6 independent real sources (§7 table, `e2e-testing-guide-xml.md`). SC3/SC5/SC7: already confirmed by Phases 2-3's own test suites/reconciliations and unaffected by this phase (no code touched their concerns) — not independently re-proven live here, consistent with the breakdown's own AC6 note that these were "already confirmed." SC7 additionally got an incidental live confirmation via NCBI's real external-DTD `<!DOCTYPE>` parsing safely. |

## 9. Needs Your Eyes

- **Three real, currently-live findings, none of them bugs in this feature, all format-agnostic (would affect equivalent JSON APIs identically), none fixed this phase (Rule 2/6 — out of scope):**
  1. **The base-URL/path gotcha** (DNB) — any single-fixed-endpoint API hits a misleading `422 API_CONN_051` (blames `data_root_path` when the real cause is the base URL/path split) if configured naively. Confirmed recurring, in a milder form (format-detection mismatch rather than an outright error), across 4 of the 6 APIs tested. Worth a follow-up: detect an error/diagnostics-shaped zero-record response distinctly from a genuinely empty one.
  2. **The `@attr` root-level path limitation** (World Bank) — `data_root_path`/`record_count_path`/`total_pages_path`/`cursor_response_path`/`next_url_response_path`'s dot-notation validator (`^[\w]+(\.[\w]+)*$`) cannot express an `@`-prefixed attribute segment, so any real API expressing pagination/count metadata as a root-level XML attribute can't wire that specific value up (the endpoint still works via the existing record-count fallback). Worth a follow-up: relax the validator to allow a leading `@` per segment, or document as accepted.
  3. **The scalar-record schema gap** (NCBI) — `data_root_path` resolving to a list of scalars (not objects) silently produces zero schema fields, then blocks Data Preview with a `422` that doesn't point back at the real cause.

  All three are documented in detail, with exact reproduction steps, in `docs/e2e-testing-guide-xml.md` §8.
- **The pre-existing `highlightJson` bug** (found during P4.A-03, unrelated to XML, not fixed — see §4) remains open and affects every JSON-configured endpoint's Raw Response panel today, not just this feature's surface.
- **P4.B was executed via direct API calls, not literal browser clicks**, across all 6 APIs — see §4/§5's recorded substitution and its stated rationale. If you want the literal UI-driven version for extra confidence, it's a straightforward follow-up (the backend behavior it would exercise is already proven here) — not required to consider this phase done, in my judgment, but your call given AC3/AC4's "with a noted substitution" status.
- **7 `ConnectionProfile`, 6 `Endpoint`, 5 `PaginationConfig`, and ~60 `SchemaField` rows now exist in the local dev database** from this validation run (§6) — left in place intentionally (matches how the app's existing dev DB already carries prior manual-testing profiles, ids 1-13, unrelated to this feature) as reproducible evidence, not cleaned up. No credentials/secrets involved (all No Auth). Let me know if you'd rather I remove them.
- **SC3/SC5/SC7 were not independently re-proven live this phase** (§8's AC6 row) — they rely on Phases 2-3's own automated test suites, per the breakdown's own note that these were "already confirmed." If you want them re-walked specifically against live data too, that's additional scope beyond what P4.B-01 called for.
- **NCBI's endpoint (§4 point 8, `esearch`) never reached a fully "successful preview" state** — this is intentional (it's documenting a real gap, not a failed attempt at a working example), but if you'd prefer every section in the new guide to end at a working `Data Preview` like the other 5, `esummary` (batch fetch by explicit IDs, richer dict-shaped records) is available as an alternative, at the cost of not being pagination-driven the same way `esearch` is. Left as-is since the scalar-record finding is itself valuable content per your "various cases" request.

## 10. Suggested Commit Plan

Same precedent as the original record (recent history uses Conventional Commits). Extends the original 3-commit P4.A plan with 2 more for P4.B:

```
1. feat(endpoint): mirror response_format across frontend types and API shapes
   [unchanged from the pre-resolution record — see git diff for exact file list]

2. feat(endpoint): add response_format Select to the endpoint form
   [unchanged from the pre-resolution record]

3. feat(data-preview): render XML raw responses with XML syntax highlighting
   [unchanged from the pre-resolution record]

4. docs(e2e): add XML end-to-end validation guide across 6 real APIs

   Documents real, live validation runs against 6 independent XML
   APIs (001-xml-response-support Phase 4, P4.B) — Deutsche
   Nationalbibliothek SRU, World Bank, NCBI E-utilities, USGS
   Earthquakes, BBC News RSS, and a NOAA S3 bucket — one section per
   API mirroring e2e-testing-guide.md's own structure, chosen to
   cover every pagination strategy meaningful for a real XML source.
   Surfaced 3 real, pre-existing, format-agnostic findings only a
   live sweep across independent hosts could have found (no
   fixture/mock setup would have): a base-URL/path configuration
   gotcha for single-fixed-endpoint APIs, a dot-notation validator
   that can't express root-level XML-attribute pagination metadata,
   and a silent zero-field result when data_root_path resolves to
   scalar records. Kept as a standalone file rather than folded into
   the existing e2e-testing-guide.md, at the human's request.

   Files: docs/e2e-testing-guide-xml.md,
          docs/e2e-testing-guide.md (one-line pointer only)

   Assisted-by: claude-implementor:claude-sonnet-5 [curl] [6 live public XML APIs]

5. docs(001-xml-response-support): close out Phase 4 — implementation record

   Files: docs/features/001-xml-response-support/phases/phase-4/implementation.md,
          docs/features/001-xml-response-support/decisions.md,
          docs/_meta/active-context.md
```

Generated/lockfile changes: none this phase.

## 11. Halt — Resolved

**Original trigger** (recorded at halt time): `[REVIEW-GATE]` subphase P4.B, combined with OD-1 unresolved and no browser-automation tooling available.

**Resolution, round 1**: the human confirmed OD-1 as recommended and instructed: *"You research yourself and do what's recommended. I also want e2e-testing-guide-xml.md with various cases."* Read as: (a) OD-1 → option (a), DNB SRU + `CursorStrategy`, as the breakdown recommended; (b) execute P4.B-01 autonomously using whatever research/tooling is available, rather than waiting for a human to drive the UI; (c) produce the P4.B-02 documentation as a new, separate file with multiple cases, not a single walkthrough section folded into the existing guide. Executed against DNB SRU — see §3/§4/§7's DNB evidence.

**Resolution, round 2**: the human followed up: *"I also want e2e-testing-guide-xml.md with various cases, urls, similar to that of json, search various xml based api responses."* Read as: match `e2e-testing-guide.md`'s breadth — one section per real API — not just the single DNB walkthrough. Researched and validated 5 more real, live, unauthenticated XML APIs (World Bank, NCBI E-utilities, USGS Earthquakes, BBC News RSS, a NOAA S3 bucket), chosen to cover every pagination strategy meaningful for a real XML source, and rewrote `docs/e2e-testing-guide-xml.md` as 6 full per-API sections mirroring the main guide's structure exactly. This surfaced 2 additional real, format-agnostic findings beyond DNB's — see §1/§4/§9.

Executed accordingly — see §3/§4/§7 for the full run and its evidence across all 6 APIs, and `docs/e2e-testing-guide-xml.md` for the complete human-facing record. Phase is now READY FOR REVIEW in full.
