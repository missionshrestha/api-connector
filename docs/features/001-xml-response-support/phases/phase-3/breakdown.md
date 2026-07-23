# Schema Inference & Data Preview Integration — Breakdown

Feature: `001-xml-response-support` · Phase 3 of 4: Schema Inference & Data Preview Integration
Branch: `001-xml-response-support` · Generated against commit `d4f20fe848b8123d2028c526eaccfe09aa831bc4`
Previous phase: Phase 2 (XML Parsing Core & Format Routing) — Reconciled 🟢 GREEN, committed (`5d241ed`). Confirmed reality: `PaginationEngine.paginate()` branches on `endpoint.response_format` at the single parse chokepoint (`engine.py:146-163`), yielding `(records, body)` where `body` is the namespace-stripped, list-coerced dict/list for XML exactly as `response.json()` produces for JSON — the original XML text is not preserved anywhere past that point. `detect_data_root()` was independently reconfirmed unchanged. `xmltodict` is the sole XML-parsing call site (`services/xml_parser.py`).
Next phase: Phase 4 — Frontend & End-to-End Validation (for continuity only; not broken down here)
Source: `plan.md` §8 Phase 3

---

## 1. Phase Context

**Purpose & Outcome**: Prove the plan's "zero downstream changes" bet (DEC-1) holds for `SchemaInferenceEngine` and the 3 body-reading pagination strategies (`Cursor`, `NextURL`, `PageSize`'s `total_pages_path`) against real, normalized XML bodies — and implement the one place that genuinely does need a change: preserving the endpoint's original XML response text for the "Raw Response" preview panel, instead of a JSON reinterpretation of the parsed body (DEC-6). Outcome: an XML-configured endpoint reaches full schema-inference and data-preview parity with a JSON endpoint, backend-only (the endpoint form UI still won't expose `response_format` for editing until Phase 4).

**Dependencies**: Needs Phase 2's format routing and confirmed-reconciled `xml_parser.py`/`response_format` field (`decisions.md` DEC-8, `phases/phase-2/reconciliation.md`). Phase 2's Reconciler carry-forward is the direct trigger for this phase's one production change: `paginate()` currently yields the normalized `body`, never the original XML text, and nothing today threads `response.text`/`response.content` past the yield to `DataPreviewService`. Produces: a fully functional XML data-preview and schema-inference pipeline for Phase 4 to surface in the UI (matching plan.md §9's "After Phase 3" deployment milestone).

**Scope calibration note**: Lean. 5 atomic tasks across 2 subphases, 1 `[REVIEW-GATE]`, 0 `[IRREVERSIBLE]` tasks — well under the escalation threshold. Per plan.md §8, this phase is "primarily validation against Phase 1/2's already-made decisions," not new design work; the one real decision (how `DataPreviewService` recovers raw XML text past the generator's yield) is surfaced below, not silently picked.

**Already resolved by reading the current code, not left as open questions**:

1. **`detect_data_root()` needs no further verification here.** Phase 2's Reconciler already reconfirmed it operates purely on `isinstance(dict)`/`isinstance(list)` checks with zero JSON-specific logic (`phases/phase-2/reconciliation.md` §3) — "Phase 3 can rely on this without re-verifying." No task added for this.
2. **`extract_records_at_path`/`get_at_path` need no further verification here.** Both were exercised end-to-end against XML in Phase 2's `TestPaginationEngineXml` (`NoPaginationStrategy`/`OffsetLimitStrategy` cases) and Phase 1's spike. This phase extends that same style of end-to-end proof to the 3 strategies Phase 2 didn't yet cover (P3.A-01) and to `SchemaInferenceEngine` (P3.A-02) — not because either function is expected to need a change, but because "expected to work" and "proven to work" are different claims, and SC3/SC4 require the latter.
3. **`PaginationEngineError`'s Phase-2 message-text change** (now format-aware instead of hard-coded "non-JSON") is a Phase 4 frontend/e2e concern per Phase 2's own carry-forward note, not something this phase re-litigates.

---

## 2. Open Decisions

**OD-1: How does `DataPreviewService` recover the original XML response text, given `PaginationEngine.paginate()`'s yield currently discards it?**

Context: Phase 2's Reconciler flagged this exact gap as Phase 3's job to resolve against the actual code (`phases/phase-2/reconciliation.md` §3): `paginate()` yields `(records, body)` where, for an XML endpoint, `body` is already the namespace-stripped/list-coerced dict — the original XML text `response.text`/`response.content` is available locally inside `paginate()`'s loop but not exposed past the yield anywhere.

Options considered:
- **(a) Extend the yielded tuple to `(records, body, raw_response_text)`.** The most conventional Python-generator change, but the widest blast radius: every existing call site that unpacks `paginate()`'s output would need updating for the new arity — `schema_inference/engine.py`'s `_fetch_sample()` (1 production site), plus roughly 30 test-level unpacks/mock-tuples across `test_pagination_engine.py` (its `collect_pages()` helper and ~14 individual `for records, _ in ...` unpacks), `test_edge_cases.py` (2 sites), and every `mock_paginate_generator`-based fixture in `test_data_preview.py` (~13 tests constructing 2-tuple `(records, body)` pages) — all for callers that don't care about raw text at all.
- **(b) A `dict` subclass wrapping the normalized `body` for XML endpoints, carrying the raw text as a non-key instance attribute** (e.g. `body.raw_response_text = response.text`). Touches zero test call sites and zero other production call sites — `isinstance(dict)` checks and key iteration are unaffected. Rejected: this is an implicit channel with no precedent anywhere else in this codebase; a future change that reconstructs or copies the body (`dict(body)`, a deep copy, a `json.loads(json.dumps(body))` round-trip) would silently drop the attribute with no error, quietly reverting XML endpoints back to a JSON reinterpretation with no failure signal — a real Correctness risk, not just a style preference.
- **(c) [RECOMMENDED] An optional `raw_response_sink: dict | None = None` out-parameter on `paginate()`.** The caller pre-creates a plain `dict` and passes it in; the engine writes `sink["text"] = response.text` every page (overwritten each iteration, so it holds the last page's text once iteration stops — mirroring how callers already track "last raw body" today). Every existing call site that doesn't pass this parameter — including `schema_inference/engine.py`'s `_fetch_sample()` and every existing test — is completely unaffected; no arity change, no mechanical test updates. `PaginationEngine` remains stateless (the mutable dict is caller-owned, never stored on `self`), preserving its documented "thread-safe; create one instance and reuse" contract (`engine.py:59-60`).

Recommendation: (c), weighed against the Decision Priority Order — **Correctness** ((b)'s silent-attribute-loss failure mode has no error signal, a real risk); **Reliability** ((c) leaves ~30 existing test assertions and 1 existing production call site completely untouched — the smallest possible blast radius for a chokepoint Phase 2 already flagged `[REVIEW-GATE]` once); **Maintainability** (an explicit, typed, optional parameter is more self-documenting than a hidden dict-subclass attribute; `row_limit`'s existing optional-parameter shape on the same method is the closest available precedent to adapt from, even though "mutable out-parameter" itself has no prior instance in this codebase). Tied to subphase **P3.B `[REVIEW-GATE]`** — confirm before P3.B-01 is implemented; the tasks below are written against option (c).

---

## 3. Subphases & Atomic Tasks

### P3.A — Integration Validation

**Objective**: Prove, with real end-to-end tests (not hand-typed dict fixtures), that `SchemaInferenceEngine` and the 3 body-reading pagination strategies (`CursorStrategy`, `NextURLStrategy`, `PageSizeStrategy`'s `total_pages_path`) require zero code changes to work against normalized XML bodies — closing the gap Phase 2's `TestPaginationEngineXml` left open (it only exercised `NoPaginationStrategy`/`OffsetLimitStrategy`).
**Deliverables**: 3 new test methods extending `TestPaginationEngineXml`; 1 new end-to-end `SchemaInferenceEngine` test class.
**Complexity/risk**: Low — test-only, no production code expected to change (FR5). The only real risk is a false sense of confidence if the new tests reuse hand-typed dicts instead of genuinely normalized XML output; every task below requires driving the real `parse_xml_response()`/`PaginationEngine.paginate()` path, not a shortcut.

```
Task ID:                  P3.A-01
Title:                    Extend TestPaginationEngineXml — Cursor/NextURL/PageSize parity  [P]
Description:              In `backend/tests/test_pagination_engine.py`'s existing
                          `TestPaginationEngineXml` class (currently covers only
                          `NoPaginationStrategy`/`OffsetLimitStrategy`, lines 219-335), add 3
                          new test methods driving `PaginationEngine.paginate()` end-to-end
                          (real `httpx_mock` + `EndpointFactory(response_format=
                          ResponseFormat.XML)`, mirroring the existing class's pattern — not
                          `test_pagination_strategies.py`'s hand-typed-dict unit style) for the
                          3 strategies whose `next_params()`/`is_complete()` read values out of
                          `response.raw_body` via `get_at_path()` (`strategies.py:24-40`):
                          `CursorStrategy` (reads `cursor_response_path`), `NextURLStrategy`
                          (reads `next_url_response_path`), and `PageSizeStrategy` configured
                          with `total_pages_path`. Each test's XML fixture must place the
                          cursor/next-URL/total-pages value at a nested XML element that
                          normalizes to the exact dot-path the strategy is configured with
                          (extend or parallel the existing `_xml_page()` helper, e.g. a
                          `<meta><cursor>...</cursor></meta>` sibling to its `<data>` root — do
                          not hand-author unrelated XML shapes).
Why This Matters:         SC3 requires these 3 body-reading strategies — not just the 2 Phase
                          2 already covered — to work against XML; an untested strategy
                          silently working or silently breaking are indistinguishable without
                          a real assertion, and DEC-1's single-chokepoint bet depends on every
                          consumer being proven, not just the two already exercised.
Dependencies:             None (Phase 2 complete; only reads what P2 already shipped)
Inputs/Preconditions:     `test_pagination_engine.py`'s `TestPaginationEngineXml` class and
                          `_xml_page()` helper (confirmed, lines 34-40/219-247);
                          `CursorStrategy`/`NextURLStrategy`/`PageSizeStrategy` (confirmed,
                          `strategies.py:97-211`); `get_at_path()` (confirmed,
                          `strategies.py:24-40`).
Output/Artifact:          3 new passing test methods in `TestPaginationEngineXml`; verifiable
                          by `pytest tests/test_pagination_engine.py -v` showing all pass with
                          zero change to any strategy or engine production code.
Placeholders:             None
Decision Type:            None — pure test coverage, no design choice.
Security & Observability: N/A — test-only change, no production code path touched.
Testing Notes:            Happy path per strategy: cursor present → next page requested with
                          the correct param; next_url present → `_next_url` sentinel followed;
                          `total_pages_path` resolved → stops at the declared page count. Edge
                          cases mirroring `test_pagination_strategies.py`'s existing per-strategy
                          unit coverage: cursor `None`/empty stops pagination; `total_pages_path`
                          absent falls back to record-count comparison. If any of the 3 does NOT
                          resolve correctly against a normalized XML body, that is evidence of a
                          bug in `xml_parser.py`'s namespace-stripping/list-coercion (DEC-8), not
                          a reason to add XML-aware branching to the strategy classes (FR5) —
                          report it as a finding, don't silently patch around it.
```

```
Task ID:                  P3.A-02
Title:                    Add SchemaInferenceEngine.infer() end-to-end test for an XML-
                          configured endpoint  [P]
Description:              In `backend/tests/test_schema_inference.py`, add a new test class
                          (paralleling `TestPaginationEngineXml`'s httpx_mock-driven pattern,
                          not the file's existing DB-mocked `_fetch_sample` orchestration
                          tests) that calls `SchemaInferenceEngine().infer(endpoint,
                          auth_handler, credentials)` end-to-end against an
                          `EndpointFactory(response_format=ResponseFormat.XML,
                          data_root_path=...)` backed by `httpx_mock` returning Phase 1's real
                          fixture (`docs/features/001-xml-response-support/phases/phase-1/
                          spike/sample.xml` — the same DNB SRU sample `test_xml_parser.py`
                          already reuses; do not hand-author a new one). Assert the resulting
                          `SchemaFieldSpec` list contains the expected key paths and the
                          confirmed sentinel-driven behavior (`dc.creator` → non-"string"
                          because it coerces to a list at least once across the 3 records, per
                          `test_xml_parser.py`'s `test_dc_creator_single_absent_multi_
                          coerces_to_lists` 1/absent/2 proof) — proving `_walk_record()`/
                          `_infer_type_from_values()` need zero XML-aware changes (FR5).
Why This Matters:         SC4 requires schema inference to produce a sane field list for XML
                          endpoints; `_walk_record`/`_infer_type_from_values` were designed and
                          tested only against hand-typed JSON-shaped dicts
                          (`TestWalkRecord`/`TestInferTypeFromValues`) — this is the first test
                          that actually drives them with a real normalized XML body.
Dependencies:             None (Phase 2 complete)
Inputs/Preconditions:     `phases/phase-1/spike/sample.xml` (confirmed, reused by
                          `test_xml_parser.py`); `SchemaInferenceEngine.infer()`/
                          `_walk_record()` (confirmed, `schema_inference/engine.py:
                          107-145,201-307`); `EndpointFactory` (confirmed,
                          `tests/factories.py`).
Output/Artifact:          A new passing test class in `test_schema_inference.py` asserting
                          concrete key paths/types/sentinels from the real XML sample;
                          verifiable by `pytest tests/test_schema_inference.py -v`.
Placeholders:             None
Decision Type:            None — pure test coverage.
Security & Observability: N/A — test-only.
Testing Notes:            Happy path: the 3-record DNB sample infers a field list where
                          `dc.creator` reflects its list-coerced nature (never inferred as a
                          plain scalar type), confirming FR4's single/multi consistency
                          guarantee actually reaches schema inference, not just
                          `xml_parser.py`'s own unit tests. Edge case: a field present in only
                          some of the 3 records (the sample's own absent-in-record-2
                          `dc:creator`) produces a non-zero `null_percentage`, exactly as an
                          equivalent JSON case already does. If inference raises or produces
                          "mixed"/unexpected types for this real, well-formed normalized
                          record, that's a genuine finding to report (plan.md §12's mitigation:
                          a Small/Medium REVISE against Phase 2, not a silent fix in
                          `SchemaInferenceEngine`).
```

### P3.B — Raw Response Preservation  [REVIEW-GATE]

**Objective**: Preserve the original XML response text through `DataPreviewService`'s `raw_response_body` output for XML-configured endpoints, per DEC-6/FR6/SC6, without altering `PaginationEngine.paginate()`'s generator contract or any existing JSON-endpoint behavior.
**Deliverables**: `raw_response_sink` out-parameter on `paginate()`; format-aware `raw_response_body` construction in `DataPreviewService.preview()`; regression + new XML test coverage.
**Complexity/risk**: Moderate blast radius, low design complexity — touches the same shared parse chokepoint Phase 2's P2.B `[REVIEW-GATE]` already modified once. The change is additive/backward-compatible by construction (OD-1 option (c)), but a mis-scoped edit here risks regressing `DataPreviewService`'s existing JSON `raw_response_body` behavior, which is why this subphase is gated.

```
Task ID:                  P3.B-01
Title:                    Add optional raw_response_sink parameter to PaginationEngine.paginate()
Description:              In `backend/api_connector/services/pagination/engine.py`, add a new
                          optional keyword parameter to `paginate()`'s signature (currently
                          `engine.py:63-71`): `raw_response_sink: dict | None = None`,
                          positioned after `row_limit` (the existing last optional parameter).
                          Immediately after `response = self._request_with_retry(...)` returns
                          (`engine.py:133-144`) and before the format-parse block (line 146),
                          add: when `raw_response_sink is not None`, set
                          `raw_response_sink["text"] = response.text` — unconditionally,
                          regardless of `endpoint.response_format` (both formats get the
                          assignment; only XML-format callers read it, per P3.B-02, keeping
                          this method itself format-agnostic and avoiding a second format
                          branch in the same function). This does not touch the parse block,
                          the `extract_records_at_path` call, `PaginatedResponse` construction,
                          or the `yield records, body` statement (line 195) — the generator's
                          yielded shape and the ADR-010 contract are completely unchanged;
                          every existing caller that doesn't pass `raw_response_sink`
                          (`schema_inference/engine.py`'s `_fetch_sample()`, every existing
                          test) is unaffected since the parameter is optional and defaults to
                          `None`. Add `raw_response_sink` to `paginate()`'s existing docstring
                          `Args:` block (currently documents `endpoint`, `auth_handler`,
                          `credentials`, `strategy`, `safety`, `row_limit` — engine.py:75-83),
                          matching that established documentation convention rather than
                          leaving the new parameter undocumented.
Why This Matters:         DataPreviewService (P3.B-02) needs the exact original response text
                          for XML endpoints (DEC-6/SC6) — the only place that text is
                          available is here, at the point the response is fetched, since
                          `body` (what's yielded today) is already the normalized dict/list
                          with the original XML text discarded. Without this, the "Raw
                          Response" panel cannot show anything but a JSON reinterpretation for
                          XML endpoints, defeating DEC-6.
Dependencies:             None (Phase 2 complete; this is the first Phase 3 production-code
                          change)
Inputs/Preconditions:     `engine.py`'s current `paginate()` (confirmed, lines 63-223,
                          unchanged since Phase 2's `5d241ed`).
Output/Artifact:          `paginate(..., raw_response_sink: dict | None = None)` — verifiable
                          by a unit test that passes a `{}` dict, drives one page through
                          `httpx_mock`, and asserts `sink["text"]` equals the mocked response's
                          raw text exactly.
Placeholders:             None
Decision Type:            [REVERSIBLE] — additive optional parameter with a `None` default;
                          every existing call site is unaffected without modification. Chosen
                          over two rejected alternatives — see OD-1.
Security & Observability: `raw_response_sink`'s contents are exactly what `response.text`
                          returns — the same class of data this module's own docstring
                          already governs ("NEVER log response body," `engine.py:11-14`). Do
                          not log `raw_response_sink` or its contents anywhere in this task's
                          diff. This task does NOT add a second XML-parsing call site: `.text`
                          is httpx's own charset-based byte-to-string decode, not an XML parse
                          — it never touches `xmltodict`/`xml.*`. SC7/AC4's "one XXE-safe
                          parsing call site in the codebase" invariant (`services/xml_parser.py`
                          remains the sole such site) is unaffected by this task.
Testing Notes:            Happy path: sink populated with the correct text after one page.
                          Edge cases: `raw_response_sink=None` (default) → no behavior change
                          from Phase 2 — every existing `test_pagination_engine.py`/
                          `test_pagination_strategies.py`/`test_pagination_framework.py`/
                          `test_edge_cases.py` test continues passing unmodified, since none of
                          them pass this new parameter; multi-page pagination → sink holds the
                          LAST page's text once iteration stops (mirroring how callers already
                          track "last raw body" today), not the first page or a concatenation
                          of all pages.
```

```
Task ID:                  P3.B-02
Title:                    DataPreviewService preserves original XML text in raw_response_body
Description:              In `backend/api_connector/services/data_preview.py`: (1) add
                          `ResponseFormat` to the existing `from api_connector.models import
                          PaginationConfig, SchemaField` line (`data_preview.py:32`). (2)
                          Before the `engine.paginate(...)` call (`data_preview.py:179-186`),
                          create a local `raw_response_sink: dict = {}` and pass
                          `raw_response_sink=raw_response_sink` as an additional keyword
                          argument to `engine.paginate(...)`. (3) Replace Step 7's
                          unconditional `raw_response_body = json.dumps(last_raw_body,
                          indent=2, default=str)[:50_000]` (`data_preview.py:206`) with a
                          branch: when `endpoint.response_format == ResponseFormat.XML` and
                          `raw_response_sink.get("text")` is not `None`, `raw_response_body =
                          raw_response_sink["text"][:50_000]`; otherwise keep the existing
                          `json.dumps(...)` line unchanged (JSON endpoints are byte-for-byte
                          unaffected — NFR2). The 50,000-char truncation cap (NFR3) applies
                          identically to both branches — do not introduce a different cap for
                          XML.
Why This Matters:         This is the one place requirement.md FR6/DEC-6 requires an actual
                          behavior change — every other consumer in the pipeline (rows,
                          columns, schema inference) is untouched by design (DEC-1). Getting
                          this branch wrong either shows XML users a JSON reinterpretation of
                          their real response (defeating SC6) or regresses the JSON path
                          that's been in production since Phase 7.
Dependencies:             P3.B-01 (needs the `raw_response_sink` parameter to exist)
Inputs/Preconditions:     `data_preview.py`'s current `preview()` (confirmed, lines 88-227,
                          unchanged since Phase 0); `ResponseFormat` (confirmed, exported from
                          `api_connector.models.__init__`, `models/__init__.py:12,33`).
Output/Artifact:          `PreviewResult.raw_response_body` equals the original XML response
                          text (truncated at 50,000 chars) for XML-format endpoints, and is
                          unchanged JSON-serialized output for JSON-format endpoints;
                          verifiable via `DataPreviewService().preview()` against a mocked XML
                          endpoint asserting `raw_response_body` matches the mocked XML text
                          exactly (not a JSON reinterpretation).
Placeholders:             None
Decision Type:            [REVERSIBLE] — a display-layer-only change (DEC-6's own
                          reversibility note); no effect on `rows`/`columns`/`total_fetched`/
                          `has_more` or any stored data.
Security & Observability: No new PII-handling surface (NFR3) — `raw_response_body` already
                          carries the same class of data (a real API response sample) whether
                          it's the JSON or XML branch; the existing "never log rows/
                          raw_response_body/credentials" contract (`data_preview.py:18-22`)
                          applies unchanged to the XML branch. No new log calls needed.
Testing Notes:            Happy path: XML endpoint → `raw_response_body` equals the mocked
                          response's raw text (drive a real `httpx_mock` end-to-end call so the
                          actual `raw_response_sink` wiring is exercised, not just constructed
                          in isolation). Regression: JSON endpoint → `raw_response_body` is
                          byte-identical to today's `json.dumps(last_raw_body, ...)` output.
                          Edge case: XML response text longer than 50,000 chars truncates
                          identically to the existing JSON cap test's shape.
```

```
Task ID:                  P3.B-03
Title:                    Regression + XML raw-response tests for DataPreviewService
Description:              Extend `backend/tests/test_data_preview.py`'s
                          `TestDataPreviewServiceDB` class with: (a) a new test asserting that
                          for an `EndpointFactory(response_format=ResponseFormat.XML)`,
                          `PreviewResult.raw_response_body` equals the original XML text —
                          driving `DataPreviewService.preview()` end-to-end via `httpx_mock`
                          (matching `TestPaginationEngineXml`'s pattern), NOT the file's
                          existing `mock_paginate_generator`/`patch.object` mocking style,
                          since that style bypasses `PaginationEngine.paginate()` entirely and
                          would not exercise the real `raw_response_sink` wiring from
                          P3.B-01/02; (b) confirm the existing `test_raw_response_body_is_
                          last_page_json` and `test_raw_response_body_truncated_at_50k` tests
                          (JSON-format endpoints, `data_preview.py:425-464`) still pass
                          completely unmodified — the explicit zero-regression bar for this
                          subphase, matching Phase 2's own "zero regression on the JSON path is
                          the actual bar" precedent (P2.B-01's Testing Notes).
Why This Matters:         P3.B-01/02's production changes are only proven correct once a real
                          end-to-end XML case demonstrates the sink is actually wired through
                          `preview()`, not just constructed correctly in isolation — and NFR2
                          (no change to JSON-endpoint behavior) is a hard constraint that must
                          be checked by running the existing suite, not assumed from reading
                          the diff.
Dependencies:             P3.B-02
Inputs/Preconditions:     `test_data_preview.py`'s existing `TestDataPreviewServiceDB` class
                          and its `_setup()`/`_mock_engine_pages()` helpers (confirmed, lines
                          199-517); `TestPaginationEngineXml`'s `httpx_mock` pattern
                          (confirmed, `test_pagination_engine.py:218-247`, for the new
                          end-to-end style this task needs).
Output/Artifact:          New passing XML end-to-end test(s) in `test_data_preview.py`; the
                          two named existing JSON tests passing unmodified; verifiable by
                          `pytest tests/test_data_preview.py -v` and a full-suite `pytest
                          --tb=short` run showing zero regressions anywhere else in the suite.
Placeholders:             None
Decision Type:            None — test coverage only, no design choice.
Security & Observability: N/A — test-only.
Testing Notes:            Happy path: XML endpoint's `raw_response_body` matches the original
                          XML text exactly — assert it is NOT equal to `json.dumps` of the
                          normalized body, not just that it equals the expected text, to
                          actually catch a regression to the pre-P3.B behavior. Edge cases:
                          XML response with multi-page pagination — `raw_response_body`
                          reflects the LAST page's raw text, mirroring the existing JSON
                          multi-page test's "last page, not first" assertion
                          (`test_raw_response_body_is_last_page_json`); XML text longer than
                          50,000 chars truncates at exactly 50,000. Regression: existing
                          JSON-focused test classes in this file pass with zero modifications
                          to their bodies (only new imports/fixtures may be added).
```

---

## 4. Phase Acceptance Criteria & Verification

**Completion criteria** (falsifiable, traced to `requirement.md` §5 Success Criteria this phase owns):

- **AC1** (traces SC3): WHEN `PaginationEngine.paginate()` drives an XML-configured endpoint using `CursorStrategy`, `NextURLStrategy`, or `PageSizeStrategy` (with `total_pages_path` set), THE SYSTEM SHALL resolve the cursor/next-URL/total-pages value from the normalized XML body via the same `get_at_path()` dot-notation traversal used for JSON, with zero code changes to any of the 3 strategy classes.
- **AC2** (traces SC4): WHEN `SchemaInferenceEngine.infer()` runs against an XML-configured endpoint, THE SYSTEM SHALL produce a `SchemaFieldSpec` list with the same key-path/type/null-percentage/sentinel semantics it produces for an equivalent JSON body, with zero code changes to `_walk_record()` or `_infer_type_from_values()`.
- **AC3** (traces SC5, regression): WHEN `DataPreviewService.preview()` runs against a JSON-configured endpoint, THE SYSTEM SHALL produce byte-identical `rows`/`columns`/`has_more`/`total_fetched`/`raw_response_body` output to before this phase — i.e., the row/column/table logic (Steps 1-6) is unaffected by this phase's one behavior change (Step 7's XML branch).
- **AC4** (traces SC6/DEC-6/FR6): WHEN `DataPreviewService.preview()` runs against an XML-configured endpoint, THE SYSTEM SHALL return the original XML response text (not a JSON reinterpretation of the normalized body) in `raw_response_body`, truncated at 50,000 characters per the existing cap (NFR3).
- **AC5** (constraint, ADR-010, carried from Phase 2): `PaginationEngine.paginate()` remains a generator; the `raw_response_sink` addition is a purely additive optional parameter — verified by every existing test in `test_pagination_engine.py`/`test_pagination_strategies.py`/`test_pagination_framework.py`/`test_edge_cases.py` continuing to pass unmodified (none of them pass the new parameter).

**Manual verification steps** (human smoke test):

1. Via `python manage.py shell`, run `SchemaInferenceEngine()._walk_record(...)` (or a full `infer()` call, per P3.A-02) against Phase 1's `sample.xml`-derived normalized body and confirm the `dc.creator` path reflects its list-coerced nature, matching `test_xml_parser.py`'s confirmed 1/absent/2 proof.
2. Create an XML-configured `Endpoint` (`response_format="xml"`) and call `DataPreviewService().preview()` directly via `manage.py shell` against a mocked or lightweight real XML-returning URL; confirm `raw_response_body` is valid XML text (starts with the document's actual root tag or an `<?xml` prolog) — not a `{`-prefixed JSON string.
3. Repeat step 2 against an existing JSON-configured endpoint and confirm `raw_response_body` is unchanged (still JSON).

**Expected automated coverage** (described, not scripted):

- `test_pagination_engine.py`: 3 new `TestPaginationEngineXml` methods (Cursor/NextURL/PageSize against XML).
- `test_schema_inference.py`: 1 new end-to-end XML test class exercising `infer()` against the real DNB sample.
- `engine.py`: a unit test for the new `raw_response_sink` parameter in isolation (populated correctly when passed; `None` default is a complete no-op).
- `test_data_preview.py`: new XML end-to-end `raw_response_body` test(s), plus confirmation that the 2 existing JSON `raw_response_body` tests pass unmodified.
- Full-suite regression: `pytest --tb=short` shows the same pass count as Phase 2's reconciled baseline (466) plus this phase's new tests, zero new failures.

---

## 5. Handoff Note

Build against commit `d4f20fe848b8123d2028c526eaccfe09aa831bc4` on branch `001-xml-response-support`. The one `[REVIEW-GATE]` is subphase P3.B (extends `PaginationEngine.paginate()`'s signature — the same shared chokepoint Phase 2's P2.B `[REVIEW-GATE]` already touched once). No `[IRREVERSIBLE]` tasks this phase. One Open Decision (OD-1, the `raw_response_sink` mechanism) should be confirmed before P3.B-01 is implemented — the tasks as written already assume the recommended option (c); if the human prefers option (a) or (b) instead, P3.B-01/02/03 need to be revised accordingly. The implementor writes the code and tests and commits **nothing** — the human commits.

**Carried forward for Phase 4** (continuity only — not broken down here):

- Backend is now fully functional for XML endpoints via direct API calls (connection test → configure → infer → preview), matching plan.md §9's "After Phase 3" deployment milestone — the endpoint form UI still doesn't expose `response_format` for editing.
- `PaginationEngineError`'s format-aware message text (changed in Phase 2, not this phase) remains something Phase 4's frontend/e2e work should stay aware of if any UI error-matching logic depends on the old wording — not re-litigated here.
- `xmltodict`'s ~1.7x overhead vs. `ElementTree` (Phase 1, synthetic stress size only) remains unconfirmed against real SRU page sizes — Phase 4's e2e validation is still the natural place to observe this.
- Residual, already-accepted risks unchanged from DEC-5/DEC-8 (cross-namespace same-local-name key collision; the `(parent_tag, child_tag)` heuristic is document-local, not schema-aware) — not new to this phase, still live for Phase 4 to keep in mind.
