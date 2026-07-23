# XML Response Support — Plan

Feature ref: `001-xml-response-support` · Created: 2026-07-23

---

## 1. Scope Calibration

**Standard** — a feature/integration of moderate complexity: one backend chokepoint change, one new model field, and one frontend display path, but genuinely multi-layer (parsing, pagination strategies, schema inference, data preview, frontend). Not a new system; not a one-file fix.

## 2. Core Approach & Components

One XML→dict/list normalization function, inserted at the single existing chokepoint (`PaginationEngine.paginate()`, `engine.py:146`), converting XML into the exact same `dict`/`list` shape `response.json()` already produces (namespaces stripped, repeated elements coerced to lists, attributes/text handled via a documented convention). Everything below that line — `extract_records_at_path`, all 6 pagination strategies, `SchemaInferenceEngine`, `DataPreviewService` — requires no logic changes. A new persisted `Endpoint.response_format` field routes to the correct parser and (for XML) preserves the original raw text for the preview panel.

Components touched:
- New: XML parsing/normalization module (backend `services/` layer, alongside `http_client.py`/`ssrf.py`/`encryption.py` as a new sibling concern).
- Modified: `PaginationEngine.paginate()` (format branch at the existing parse site), `Endpoint` model + migration + serializers, `DataPreviewService` (raw-body preservation for XML), endpoint form UI, `RawResponseViewer`.
- Unmodified (by design): `extract_records_at_path`, `get_at_path`, all 6 pagination strategy classes, `SchemaInferenceEngine._walk_record`/type inference, `DataPreviewService`'s row/column/table logic, the 6-step connection test diagnostic.

## 3. High-Level Data Flow

```
httpx.Response (XML or JSON body, from BaseHTTPClient — unchanged)
   → PaginationEngine.paginate(): format branch on endpoint.response_format
       JSON → response.json()                      (unchanged)
       XML  → xml_to_dict(response.text)            (new; XXE-safe, namespace-stripped,
                                                       single-vs-list coerced)
   → same dict/list shape either way
   → extract_records_at_path(body, endpoint.data_root_path)   (unchanged)
   → yielded records + raw_body                                (unchanged)
   → SchemaInferenceEngine._walk_record(...)                   (unchanged)
   → DataPreviewService: rows/columns/table                    (unchanged)
   → DataPreviewService: raw_response_body
       JSON → json.dumps(raw_body)                  (unchanged)
       XML  → original response.text preserved       (new)
```

## 4. Where the Complexity Lives

The XML→dict/list normalization convention itself: (a) namespace stripping without silently colliding same-named elements from different namespaces, (b) coercing a single occurrence of a repeated element into a list consistently with multiple occurrences (XML has no native array — this ambiguity doesn't exist in JSON and is the main source of subtle bugs), and (c) a documented attribute/text-content convention that produces sane, predictable dot-notation paths for schema inference to flatten. Stage 3 should invest the most task-level detail here, in Phase 2.

## 5. Build Order Rationale

Phase 1 (spike) must precede real implementation because the riskiest assumption — that normalizing real-world XML (especially namespaced SRU/MARCXML shapes) into dict/list works cleanly with zero downstream changes — is cheap to falsify early and expensive to discover wrong after Phases 2-4 are built around it. Phase 2 (parsing core + format routing) must precede Phase 3 (schema/preview integration) because integration testing needs the format branch and normalized output to exist. Phase 4 (frontend + e2e) is last because it validates the complete, already-integrated backend pipeline against a real API rather than mocks.

## 6. Technical Spike

**Question**: Does normalizing real-world XML (namespaced, SRU/MARCXML-shaped) into the same `dict`/`list` convention `response.json()` produces let the existing dot-notation traversal (`extract_records_at_path`-style resolution) and a schema-inference-style flatten work without any bespoke XML-aware code beyond the normalization function itself?

**Test**: Take a real, representative XML sample (ideally an actual captured SRU response body) and run it through a candidate library + convention (namespace-strip, attribute/text-content handling, single-vs-list coercion) using throwaway code — not production wiring. Confirm dot-notation can resolve the record root and that a schema-inference-style flatten produces sane, non-colliding field paths.

**Go/no-go gate**: Go — proceed to Phase 2 with the confirmed conventions. No-go — the single-chokepoint/zero-downstream-changes design doesn't hold for realistic XML; this surfaces back to Requirement Architect via Reconciler escalation as a Large REVISE (the riskiest assumption was wrong by definition), likely requiring bespoke XML-aware traversal in one or more downstream layers.

**Time-box**: ~2-3 AI-assisted hours.

**Sequence position**: Phase 1, before any production code is written.

## 7. Phase Overview

| Phase | Name | Purpose | Key Dependencies | Expected Outcome | Effort |
|---|---|---|---|---|---|
| 1 | Technical Spike: XML Normalization Feasibility | Validate the riskiest assumption before building around it | None | Go/no-go decision + confirmed normalization conventions | 2-3 hrs |
| 2 | XML Parsing Core & Format Routing | Production XXE-safe converter wired into `PaginationEngine`; new `response_format` field | Phase 1's confirmed conventions | Format-aware pagination fetch working for XML endpoints | 6-10 hrs |
| 3 | Schema Inference & Data Preview Integration | Prove zero-downstream-changes bet; fix the one place that does need a change (raw preview) | Phase 2 | Schema inference + data preview fully functional for XML | 4-6 hrs |
| 4 | Frontend & End-to-End Validation | Surface `response_format` and XML raw text in UI; validate against a real API | Phase 3 | Full flow (test → configure → infer → preview) works end-to-end against a real XML API | 3-5 hrs |

## 8. Phase Descriptions

### Phase 1 — Technical Spike: XML Normalization Feasibility

**Purpose & Outcome**: De-risk the plan's core architectural bet before committing Phases 2-4 to it. Outcome is a go/no-go decision plus a confirmed, documented normalization convention (namespace handling, attribute/text-content shape, single-vs-list coercion rule) that Phase 2 implements for real.

**Subphase Summaries**:
- P1.A — Candidate library/approach trial. Try a candidate XML→dict conversion approach (e.g. `defusedxml`-based ElementTree walk, or `xmltodict` over a defused parser) against a real or representative namespaced XML sample; observe the raw output shape.
- P1.B — Convention validation. Apply namespace-stripping and single-vs-list coercion to the trial output; confirm a `data_root_path`-style dot-notation string can resolve the record root, and that a flatten pass produces sane, non-colliding field paths a user could meaningfully configure `SchemaField`s against.

**Key Decisions**: Exact library/approach (deferred to this phase, informed by Requirement §10's `defusedxml` assumption); precise attribute/text-content key convention (e.g. `@attr`/`#text` vs. an alternative) — identified here, decided based on what the real sample actually needs.

**Dependencies**: None (foundation phase). Produces: the confirmed convention Phase 2 builds against.

**Artifacts**: Throwaway trial code + a short written note of the confirmed convention (not production code — Phase 2 builds the real module).

**Effort**: 2-3 AI-assisted hours.

---

### Phase 2 — XML Parsing Core & Format Routing

**Purpose & Outcome**: Production XML→dict/list converter wired into the pagination pipeline as a format branch, replacing the hard-coded `.json()` call, plus the persisted config field that drives the routing.

**Subphase Summaries**:
- P2.A — XML parsing module. XXE-safe parse (`defusedxml`-based per Requirement NFR1) implementing the conventions confirmed in Phase 1 — namespace-strip, attribute/text handling, single-vs-list coercion. New sibling module to `http_client.py`/`ssrf.py`/`encryption.py`.
- P2.B — `PaginationEngine` format branch. `[REVIEW-GATE]` (modifies the IRREVERSIBLE generator-based `paginate()` contract's parse site — must preserve yield/generator semantics exactly). Branch on `endpoint.response_format` at the current `response.json()` call site (`engine.py:146`); update the `PaginationEngineError` message to be format-aware instead of hard-coded to "non-JSON."
- P2.C — `Endpoint.response_format` field. `TextChoices` field (ADR-003 pattern) + additive migration + serializer validation, defaulted at endpoint-creation time from `ConnectionProfile.last_test_detected_format`, user-editable thereafter.

**Key Decisions**: Whether `detect_data_root()`'s auto-suggest logic needs an XML-aware variant, or works unchanged once the body is already normalized to dict/list (likely unchanged, per the core approach — confirm during this phase, not before).

**Dependencies**: Needs Phase 1's confirmed conventions. Produces: the format-routing and normalized-body output every later phase consumes.

**Artifacts**: XML parsing module; `PaginationEngine` format branch; `Endpoint.response_format` field + migration + serializer changes.

**Effort**: 6-10 AI-assisted hours — the most novel code in the feature.

---

### Phase 3 — Schema Inference & Data Preview Integration

**Purpose & Outcome**: Prove the "zero downstream changes" bet holds end-to-end for schema inference and pagination strategies, and implement the one place that does need a real change — the raw-response preview.

**Subphase Summaries**:
- P3.A — Integration validation. Exercise `SchemaInferenceEngine` (`_walk_record`, sentinels, type inference) and the pagination strategies' body-reading paths (`Cursor.next_params`, `NextURLStrategy.next_params`, `PageSizeStrategy`'s `total_pages_path`) against normalized XML bodies. Expected: no logic changes needed, per Phase 1's spike finding — fix anything that doesn't hold and note it as a plan deviation if the fix is non-trivial.
- P3.B — Raw response preservation. `DataPreviewService` preserves the original XML response text for XML-format endpoints instead of `json.dumps`-reserializing the normalized body (`data_preview.py:206`), surfaced through the existing `raw_response_body` field.

**Key Decisions**: None expected to be novel — this phase is primarily validation against Phase 1/2's already-made decisions.

**Dependencies**: Needs Phase 2's format routing. Produces: a fully functional XML data-preview and schema-inference pipeline for Phase 4 to surface in the UI.

**Artifacts**: Passing tests against XML fixtures for schema inference and all 6 pagination strategies; format-aware `raw_response_body`.

**Effort**: 4-6 AI-assisted hours.

---

### Phase 4 — Frontend & End-to-End Validation

**Purpose & Outcome**: Surface XML support in the UI where it's currently silently JSON-only, and validate the complete flow against a real public XML API.

**Subphase Summaries**:
- P4.A — UI surfacing. Endpoint form exposes `response_format` (view/edit, matching the existing endpoint-config-field pattern); `RawResponseViewer` renders XML text as XML (not JSON-formatted) when `response_format === "xml"`.
- P4.B — End-to-end validation. `[REVIEW-GATE]` (external network dependency, not fully reproducible/deterministic like the rest of the test suite). Full flow — connection test → configure `data_root_path` → schema inference → data preview — against a real SRU or comparably namespaced public XML API, mirroring the existing `docs/e2e-testing-guide.md` pattern (e.g. the documented DummyJSON pagination footgun).

**Key Decisions**: Which specific public XML API to validate against (deferred to task level — pick one that's stable/free and genuinely namespaced, not a toy example).

**Dependencies**: Needs Phase 3. Produces: user-facing completion of the feature.

**Artifacts**: Updated endpoint form + `RawResponseViewer`; an e2e validation note (addendum to or new section in `docs/e2e-testing-guide.md`).

**Effort**: 3-5 AI-assisted hours.

## 9. Deployment Milestones

- **After Phase 3**: backend fully functional for XML endpoints via the API directly (connection test, pagination, schema inference, data preview all work) — deployable to any consumer that talks to the API directly, with the caveat that the endpoint form UI doesn't yet expose `response_format` for editing (would need direct API calls or DB access to set it).
- **After Phase 4**: fully shippable to end users — UI-configurable, validated against a real external API.

## 10. Dependency Map & Parallelism

Critical path is fully linear: Phase 1 → 2 → 3 → 4. No parallelizable phases — each phase's implementation depends on the prior phase's confirmed output (conventions → routing → integration → UI). `[VOLATILE]`: Phase 1's chosen library/convention is the one area later phases are most sensitive to; a convention change discovered in Phase 2 or 3 should be fed back into a short Phase 1 addendum rather than patched ad hoc in place.

## 11. Expected Final State

- `Endpoint.response_format` — TextChoices field, migrated, serializer-validated, UI-editable. ⬜
- XML parsing module — XXE-safe, namespace-stripping, single-vs-list-coercing, sole XML-parse call site in the codebase. ⬜
- `PaginationEngine.paginate()` — format-aware branch at the parse chokepoint; generator contract (ADR-010) unchanged. ⬜
- `extract_records_at_path`, `get_at_path`, all 6 pagination strategies, `SchemaInferenceEngine`, `DataPreviewService`'s row/column logic — zero code changes, confirmed working against XML via tests. ⬜
- `DataPreviewService.raw_response_body` — format-aware (original XML text for XML endpoints). ⬜
- `RawResponseViewer` / endpoint form — `response_format`-aware UI. ⬜
- End-to-end validation against a real public XML API — passed, documented. ⬜
- **Final check** (on Phase 4 completion): re-run Requirement §5 success criteria SC1-SC8 against the completed feature; all must hold.

## 12. Risks & Open Questions

- **Risk**: Phase 1's spike sample may not be representative enough of the eventual real-world APIs this gets used against (e.g. a sample lacking mixed content or unusual attribute usage that a later real API has). Mitigation: if Phase 4's e2e validation surfaces a normalization gap the spike missed, treat it as a Small/Medium REVISE against Phase 2, not a reason to distrust the whole design.
- **Risk**: XXE-safe library choice (deferred to Phase 1/2) could have API/performance characteristics that don't fit cleanly into the synchronous `httpx`-based request loop. Mitigation: Phase 1's spike is the checkpoint for this before Phase 2 commits to a specific library.
- **Open question deferred to task level**: exact attribute/text-content key convention (Phase 1 decides based on real sample; not resolved here).
- **Open question deferred to task level**: which public XML API Phase 4's e2e validation targets.
- **Known unknown**: whether `detect_data_root()`'s auto-suggest logic needs XML-specific handling or works unchanged post-normalization — flagged in Phase 2, not resolved here.
