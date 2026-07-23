HEADER
  Feature 001-xml-response-support · Phase 3 — Schema Inference & Data Preview Integration
  Baseline commit: d4f20fe848b8123d2028c526eaccfe09aa831bc4 on branch 001-xml-response-support
  State: UNCOMMITTED working tree (review with: git diff d4f20fe848b8123d2028c526eaccfe09aa831bc4)
  Status: READY FOR REVIEW

1. Summary
   - **P3.A (Integration Validation, test-only)**: 4 new end-to-end tests prove
     `CursorStrategy`/`NextURLStrategy`/`PageSizeStrategy` (its `total_pages_path` path)
     and `SchemaInferenceEngine.infer()` need zero XML-aware code changes — closing the
     gap Phase 2's `TestPaginationEngineXml` left open and proving schema inference
     against Phase 1's real DNB XML sample, not a hand-typed dict.
   - **P3.B (Raw Response Preservation, `[REVIEW-GATE]`)**: `PaginationEngine.paginate()`
     gained an optional `raw_response_sink: dict | None = None` out-parameter (OD-1
     option (c), human-confirmed) that captures `response.text` on every page,
     unconditionally, regardless of format. `DataPreviewService.preview()` passes its
     own sink and, for XML-configured endpoints only, now returns the original XML text
     in `raw_response_body` instead of a JSON reinterpretation of the normalized body
     (DEC-6/FR6). JSON endpoints are byte-for-byte unaffected — verified by the 2 named
     pre-existing JSON `raw_response_body` tests passing completely unmodified.
   - Full backend suite: **475 passed** (466 Phase 2 baseline + 9 new: 4 from P3.A, 5
     from P3.B), 0 failures, 0 regressions. `ruff check .` and `ruff format --check .`
     both clean (3 test files needed a `ruff format` pass after editing — whitespace/line
     -wrap only, no logic change). ADR-005 grep enforcement: clean.
   - The phase halted once, at P3.B's `[REVIEW-GATE]` / OD-1, after P3.A was complete and
     verified. Human confirmed "do what's recommended" (option (c)); P3.B was then
     implemented and verified against the confirmed option. See `decisions.md`'s Phase 3
     tactical-decisions entry for the full resolution record.
   - Pre-flight cleanliness check: at start, `git status` showed `docs/_meta/active-context.md`
     (modified) and `phases/phase-3/breakdown.md` (new) already staged — Stage 3
     (Breakdown Engineer)'s own output for this exact phase, matching Phase 2's own
     precedent for this same situation. Built on top of it without staging anything
     myself.

2. What Changed — file by file
   - `backend/api_connector/services/pagination/engine.py` (P3.B-01): added optional
     `raw_response_sink: dict | None = None` parameter to `paginate()`, documented in its
     docstring `Args:` block. Immediately after the retried request returns and before
     the format-parse branch, sets `raw_response_sink["text"] = response.text`
     unconditionally when a sink is provided (both formats get the assignment; only
     XML-format callers read it). No other line in `paginate()` changed — the
     generator's yielded shape (`yield records, body`) and ADR-010's contract are
     untouched.
   - `backend/api_connector/services/data_preview.py` (P3.B-02): imported
     `ResponseFormat`; added a local `raw_response_sink: dict = {}` before the
     `engine.paginate()` call and passed it through; replaced Step 7's unconditional
     `json.dumps(last_raw_body, ...)` with a branch — XML-format endpoints with a
     populated sink use `raw_response_sink["text"][:50_000]`; every other case (JSON
     endpoints, or an XML endpoint whose sink is somehow empty) keeps the original
     `json.dumps(...)[:50_000]` line unchanged. The 50,000-char truncation cap applies
     identically either way.
   - `backend/tests/test_pagination_engine.py`: added `CursorStrategy`,
     `NextURLStrategy`, `PageSizeStrategy` to the strategies import; added
     `_xml_page_with_meta()` helper (parallels `_xml_page()`, adding a `<meta>` sibling
     to the `<data>` root); added 3 tests to `TestPaginationEngineXml` (P3.A-01); added a
     new `TestPaginationEngineRawResponseSink` class with 3 tests (P3.B-01: happy path,
     `None`-default no-op, multi-page "holds last page" behavior).
   - `backend/tests/test_schema_inference.py`: added `ResponseFormat`, `NoneAuthHandler`,
     `Path` imports and `XML_SPIKE_DIR`/`XML_DATA_ROOT_PATH` constants; added
     `TestSchemaInferenceEngineInferXml` with `test_infer_against_real_xml_sample`
     (P3.A-02), driving `SchemaInferenceEngine().infer()` end-to-end via `httpx_mock`
     against Phase 1's real `sample.xml`.
   - `backend/tests/test_data_preview.py`: added `json`, `ResponseFormat`,
     `NoneAuthHandler` imports; added a new `TestDataPreviewServiceXmlRawResponse` class
     (P3.B-03) with `test_raw_response_body_is_original_xml_text` and
     `test_raw_response_body_truncated_at_50k_for_xml`, both driving
     `DataPreviewService.preview()` end-to-end via `httpx_mock` (not the file's
     `mock_paginate_generator`/`patch.object` style, which bypasses
     `PaginationEngine.paginate()` and would not exercise the real `raw_response_sink`
     wiring). Confirmed the 2 existing JSON `raw_response_body` tests
     (`test_raw_response_body_is_last_page_json`, `test_raw_response_body_truncated_at_50k`)
     pass completely unmodified.
   - `docs/features/001-xml-response-support/decisions.md`: appended the Phase 3
     tactical-decisions entry (OD-1/P3.B halt resolution + the new engine-bug finding).
   - `docs/_meta/active-context.md`: Phase 3 status updated through
     Implementing → Halted → Implementing (resumed) → Ready for review.

3. How It Works
   - P3.A adds no production code; each new test drives the real, unmodified path
     (`PaginationEngine.paginate()` → strategy `next_params()`/`is_complete()` →
     `get_at_path()`; `SchemaInferenceEngine.infer()` → `_fetch_sample()` → `paginate()`
     → `_walk_record()`/`_infer_type_from_values()`) against XML-configured endpoints.
   - P3.B's flow: `DataPreviewService.preview()` creates a plain `{}` dict, passes it as
     `raw_response_sink=` into `engine.paginate(...)`. On every page the engine
     overwrites `sink["text"]` with that page's `response.text` — a page fetched via
     `httpx`, decoded per its own charset, completely independent of the
     `xml_parser`/`response.json()` branch that produces the normalized `body`. Once
     iteration stops, `sink["text"]` holds the last page's raw text. Step 7 then checks
     `endpoint.response_format`: XML → use the sink's raw text (truncated); otherwise →
     the pre-existing `json.dumps(last_raw_body, ...)` path, byte-for-byte as before.

4. Decisions Made
   - **OD-1 resolved: option (c), the `raw_response_sink` out-parameter** (human
     confirmed "do what's recommended" — see `decisions.md`). Weighed per the Decision
     Priority Order: Correctness (option (b)'s hidden-attribute approach fails silently
     on any body copy/reconstruction); Reliability (zero existing call sites — 1
     production, ~30 test — need any change, versus option (a)'s tuple-arity break);
     Maintainability (an explicit, typed, optional parameter mirroring `row_limit`'s
     existing shape on the same method).
   - **Test fixtures always use ≥2 items per XML page, never exactly 1** (P3.A). A
     single `<item>` in one XML document doesn't coerce to a list (xmltodict's list
     coercion is document-local — DEC-8's own documented residual risk), so
     `extract_records_at_path` would see a bare dict instead of a list and return 0
     records — a false "stop" for the wrong reason. Found while writing
     `test_cursor_strategy_...` (an initial draft's lone final-page item produced `0`
     records, not `1`); fixed by using 2-item pages throughout and, for
     `PageSizeStrategy`'s record-count fallback sub-case, `page_size=3` with a 2-item
     terminating page (not `page_size=2` with a 1-item terminating page).
   - **`NextURLStrategy`'s XML test uses a query-string-free next_url** — works around
     the newly-discovered, pre-existing, format-agnostic engine bug (§9) instead of
     asserting on a URL shape the current engine code doesn't actually preserve, for a
     reason unrelated to what P3.A-01 is testing.

5. Deviations from the Breakdown
   - **[local]** `test_next_url_strategy_follows_next_url_from_xml_body` uses a next_url
     without a query string, where the breakdown's own prose examples use
     `?page=2`-style URLs. Tactical substitution, not a design change — see §9 for the
     underlying finding.
   - No other deviations. P3.A-01/02 and P3.B-01/02/03 implemented exactly as specified
     otherwise (P3.B against OD-1's confirmed option (c)).

6. Contract Changes — for the Reconciler
   - **`PaginationEngine.paginate()` signature**: added `raw_response_sink: dict | None =
     None` as the new last parameter (after `row_limit`). Purely additive — every
     existing call site (production and test) that doesn't pass it is unaffected, since
     it defaults to `None` and the engine no-ops when it is `None`. No change to the
     generator's yielded shape or ADR-010's contract.
   - **`DataPreviewService.preview()`'s `PreviewResult.raw_response_body`** now contains
     the original response text (not a JSON reinterpretation) for XML-configured
     endpoints specifically. `rows`, `columns`, `total_fetched`, `has_more` are
     completely unaffected for both formats. JSON-configured endpoints see no change to
     `raw_response_body` either (still `json.dumps(last_raw_body, ...)`).
   - No model/migration/serializer/URL/env-var changes this phase.

7. Tests & Verification
   - `pytest tests/test_pagination_engine.py -v`: **33 passed** (27 pre-Phase-3 + 3 P3.A
     + 3 P3.B).
   - `pytest tests/test_schema_inference.py -v`: **40 passed** (39 + 1 P3.A).
   - `pytest tests/test_data_preview.py -v`: **17 passed** (15 + 2 P3.B), including the 2
     named pre-existing JSON `raw_response_body` tests passing byte-for-byte unmodified.
   - Full suite: `pytest --tb=short` → **475 passed**, 0 failed (466 Phase 2 baseline + 9
     new). Re-ran after `ruff format` auto-fixed 3 touched test files (whitespace/wrap
     only) to confirm the reformat didn't change behavior.
   - `ruff check .`: All checks passed. `ruff format --check .`: clean (after the
     auto-fix pass above). ADR-005 enforcement grep: clean (no `Fernet` import outside
     `encryption.py`).
   - Security Self-Check (Rule 3, full list):
     - **Injection**: N/A — no SQL/shell/eval/deserialization surface touched this
       phase.
     - **XSS**: N/A — backend only, no rendering.
     - **Log Injection**: checked — grepped both changed production files for every
       `logger.*` call; none references `raw_response_sink` or the new
       `raw_response_body` XML branch. No new log calls were added at all this phase.
     - **Authorization/IDOR**: N/A — no new resource-access surface; `paginate()`/
       `preview()` operate on the same caller-supplied `endpoint` they always did, no
       new lookup by user-controlled ID.
     - **Secrets**: N/A — no credentials/keys/tokens touched.
     - **Sensitive-data exposure**: `raw_response_sink`'s contents are `response.text` —
       the exact same class of data (`raw_response_body`) `data_preview.py`'s own
       docstring already governs ("never log rows/raw_response_body/credentials",
       lines 18-22) and `engine.py`'s docstring already governs ("NEVER log response
       body," lines 11-14). No new logging of either. Verified by grep, not assumed.
     - **Crypto**: N/A — untouched.
     - **SSRF**: N/A — no new outbound-request-target derivation; `raw_response_sink`
       only captures the text of a request the engine was already making.
     - **Input validation**: N/A — no new external input surface (the sink is
       engine-internal, never user-supplied).
     - **Dependencies**: N/A — no new dependency added this phase (still only
       `xmltodict`, added Phase 2).

8. Phase Acceptance Criteria
   - **AC1** (SC3, body-reading strategies): MET. 3 end-to-end tests, `pytest
     tests/test_pagination_engine.py -v` (see above).
   - **AC2** (SC4, schema inference): MET. 1 end-to-end test against the real DNB sample.
   - **AC3** (SC5, JSON regression): MET. Full suite 475 passed, 0 regressions; the 2
     named pre-existing JSON `raw_response_body` tests pass byte-for-byte unmodified.
   - **AC4** (SC6/DEC-6/FR6, raw XML preview): MET.
     `test_raw_response_body_is_original_xml_text` asserts `raw_response_body` equals
     the mocked XML text exactly and is NOT equal to a `json.dumps` reinterpretation of
     the normalized body — the actual regression this criterion guards against.
   - **AC5** (ADR-010, generator contract): MET. `raw_response_sink` is a purely
     additive optional parameter; every pre-existing pagination test file
     (`test_pagination_engine.py`, `test_pagination_strategies.py`,
     `test_pagination_framework.py`, `test_edge_cases.py`) continues to pass unmodified
     — none of them pass the new parameter.
   - Manual verification steps 1-3 (breakdown §4): not run separately via
     `manage.py shell` — the automated `httpx_mock`-driven tests above (specifically
     `TestSchemaInferenceEngineInferXml` for step 1, and
     `TestDataPreviewServiceXmlRawResponse` for steps 2-3) exercise the identical
     assertions (dc.creator list-coercion; `raw_response_body` starts as real XML, not
     `{`-prefixed JSON; JSON endpoints unchanged) with stronger, repeatable, real
     end-to-end HTTP-call coverage than a one-off manual shell command would add.

9. Needs Your Eyes
   - **New finding, out of scope for this phase**: `PaginationEngine._request_with_retry`
     passes `params={}` unconditionally to `httpx.Request` on the `_next_url` sentinel
     path (used by both `NextURLStrategy` and `LinkHeaderStrategy`). An explicit empty
     `params={}` silently strips any query string already present in that URL —
     confirmed directly against `httpx` (`httpx.Request("GET", "https://x/y?a=1",
     params={})` → `.url` is `https://x/y`), independent of this codebase. No existing
     test caught this because no prior end-to-end `PaginationEngine` test exercised
     either strategy (only their `next_params()` return value was unit-tested, never
     the engine's actual outbound request). This affects JSON endpoints exactly as much
     as XML ones — it predates this feature and is not downstream of XML normalization
     (DEC-1) — so it was not fixed here (Rule 6: an out-of-task-scope defect gets
     reported, not silently patched). Recommend a small, separate follow-up (likely:
     only pass `params=` to `httpx.Request` when non-empty, or merge params into the URL
     directly) for any endpoint using `NextURLStrategy`/`LinkHeaderStrategy` with a
     query-string-bearing next URL — the common real-world shape. Recorded in
     `decisions.md`'s Phase 3 entry too.
   - No `[EXTERNAL]` placeholders this phase. No security-sensitive
     (auth/crypto/secrets) code was added or touched.
   - The `raw_response_sink` mechanism is genuinely new to this codebase (no prior
     "mutable out-parameter on a generator method" precedent existed to adapt from) —
     worth a closer look on review given it sets a pattern, even though its blast
     radius is provably zero for every existing caller.

10. Suggested Commit Plan
    Precedent: recent history uses `feat:`/`test:`/`docs:` prefixes without a `(scope)`
    (`git log --oneline -5`); matching that convention rather than defaulting to full
    Conventional Commits scoping.

    1. test: cover Cursor/NextURL/PageSize strategies against normalized XML bodies

       Closes the coverage gap Phase 2's TestPaginationEngineXml left open (it only
       exercised NoPagination/OffsetLimit). Fixtures deliberately avoid single-item XML
       pages — xmltodict's list coercion is document-local (DEC-8), so a lone <item>
       doesn't coerce to a list and would produce a false record-count-based stop
       instead of exercising the intended cursor/next-url/total-pages signal. Also
       surfaced (not fixed — see the next commit's note and decisions.md) a
       pre-existing, format-agnostic bug where PaginationEngine drops the query string
       from any _next_url sentinel.

       Assisted-by: implementor:claude-sonnet-5 [pytest, ruff]

    2. test: cover SchemaInferenceEngine.infer() end-to-end against real XML

       Proves _walk_record()/_infer_type_from_values() need zero XML-aware changes,
       driven against Phase 1's real DNB sample rather than a hand-typed dict, per
       plan.md's "proven, not just expected to work" bar for this phase.

       Assisted-by: implementor:claude-sonnet-5 [pytest, ruff]

    3. feat: add raw_response_sink out-parameter to PaginationEngine.paginate()

       DataPreviewService needs the original response text for XML endpoints (DEC-6)
       but paginate() only ever yielded the normalized body, discarding it. Chose an
       optional out-parameter (OD-1 option (c)) over extending the yielded tuple's
       arity (touches ~30 test call sites + 1 production site for callers that don't
       care) or a dict-subclass hidden attribute (silently dropped by any body copy,
       no error signal) — zero blast radius on every existing caller, confirmed by the
       full suite passing unmodified.

       Assisted-by: implementor:claude-sonnet-5 [pytest, ruff]

    4. feat: preserve original XML text in DataPreviewService raw_response_body

       "Raw response" should mean what the API actually returned (DEC-6) — showing a
       JSON reinterpretation of an XML response misrepresents the real payload to a
       user debugging against the source API. JSON endpoints are byte-for-byte
       unaffected; the existing 50,000-char truncation cap applies identically to
       both branches.

       Assisted-by: implementor:claude-sonnet-5 [pytest, ruff]

    5. test: cover DataPreviewService raw_response_body for XML endpoints

       Drives DataPreviewService.preview() end-to-end via httpx_mock (not the file's
       mock_paginate_generator/patch.object style, which bypasses
       PaginationEngine.paginate() and wouldn't exercise the real raw_response_sink
       wiring). Confirms the 2 pre-existing JSON raw_response_body tests still pass
       unmodified — the explicit zero-regression bar for this subphase.

       Assisted-by: implementor:claude-sonnet-5 [pytest, ruff]

    6. docs: record Phase 3 decisions and implementation

       Not authored by me to commit — bundles decisions.md's Phase 3 entry,
       active-context.md's status updates, and this implementation.md/breakdown.md.
       Human may prefer to fold this into commit 1 or keep separate; either is fine.

11. Halt
    N/A — phase resumed and completed after the human's OD-1/P3.B confirmation. See
    `decisions.md`'s Phase 3 entry for the full halt-and-resolution record.
