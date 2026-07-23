# Breakdown — Phase 1: Technical Spike: XML Normalization Feasibility

```
Feature: 001-xml-response-support · Phase 1 of 4: Technical Spike: XML Normalization Feasibility
Branch: 001-xml-response-support  ·  Generated against commit 44a191c
Previous phase: None — this is the foundation phase.
Next phase: Phase 2 — XML Parsing Core & Format Routing (continuity only; NOT broken down here).
Source: plan.md §6, §8 (Phase 1)
```

---

## 1. Phase Context

**Purpose & Outcome**: De-risk the plan's core architectural bet — that normalizing arbitrary XML (namespaced, SRU/MARCXML-shaped) into the same `dict`/`list` convention `response.json()` produces will let the entire existing downstream pipeline (`extract_records_at_path`, `SchemaInferenceEngine._walk_record`, and by extension all 6 pagination strategies and `DataPreviewService`) work unmodified — before Phases 2-4 commit production code to that assumption (Requirement §3 Riskiest Assumption).

Outcome is a **go/no-go decision** plus a **confirmed, documented normalization convention** (library choice, namespace-stripping rule, single-vs-list coercion rule, attribute/text-content key convention) that Phase 2 implements for real. Nothing produced here is production code — see Rule 2 of this breakdown's governing prompt and plan.md §7 Phase 1 Artifacts ("throwaway trial code + a short written note... not production code").

**Dependencies**: None — this is the foundation phase; no prior phase's `reconciliation.md` exists yet (confirmed: `docs/features/001-xml-response-support/phases/` had no `phase-*` directories before this one). Produces: the confirmed convention Phase 2's production XML parsing module builds against.

**Scope calibration note**: **Compact.** Plan.md time-boxes this phase at 2-3 AI-assisted hours across 2 subphases with no production code. The breakdown below is deliberately lean — 6 atomic tasks, no `[REVIEW-GATE]`, no `[IRREVERSIBLE]` decisions — matching that scope. Do not impose Phase-2-level ceremony (migrations, serializers, production module structure) on this phase.

---

## 2. Open Decisions

None requiring human resolution before this phase starts. Two items look like open decisions but are not:

- **Exact XXE-safe library** (`defusedxml.ElementTree` walk vs. `xmltodict` over a defused parser): `decisions.md` DEC-2 already decided the *approach* (an XXE-safe, `defusedxml`-family parser) and explicitly deferred only the *specific package* to this phase's empirical trial (Task P1.A-02). This is the phase's own deliverable, not a pre-implementation choice for the human to make blind.
- **Attribute/text-content key convention** (e.g. `@attr`/`#text`): `requirement.md` §10 flags this as `[ASSUMPTION]` "to be confirmed in Phase 1's spike against a real sample" — again, this phase's job to resolve empirically (Task P1.B-01), not a blind pre-choice.

Both are decided by trial-and-observation in the tasks below and written up in `spike-findings.md` (Task P1.B-04). **At human review of this phase**, promote the confirmed choices into `decisions.md` as a new `DEC-8` entry (Origin: Breakdown Engineer · Phase 1 · REVISE) before Phase 2's breakdown is generated — see Handoff Note.

---

## 3. Subphases & Atomic Tasks

### P1.A — Candidate Library/Approach Trial

Objective: Obtain a real, representative namespaced XML sample and run a candidate XXE-safe library over it via throwaway code, observing the raw output shape before any normalization convention is applied.
Deliverables: one sample XML file; one throwaway trial script producing an unnormalized dict/list dump of that sample.
Complexity/risk: low — no production code touched; the only real risk is picking a sample that isn't representative enough (plan.md §12 names this explicitly as a residual risk even after this phase).

```
Task ID:                  P1.A-01
Title:                    Assemble a representative namespaced XML sample  [P]
Description:              Obtain or construct one XML document representative of the
                          confirmed target use case (government/public-data SRU APIs,
                          requirement.md §5 Stakeholders). Prefer an actual captured
                          response body from a real, public SRU (or comparably
                          namespaced, e.g. MARCXML-shaped) endpoint over a hand-authored
                          sample — plan.md §6 Test states this preference explicitly;
                          exact source endpoint is left to the implementor (mirrors how
                          Phase 4's e2e target API is also deferred to task level, per
                          plan.md §8 Phase 4 Key Decisions). The sample MUST exhibit, at
                          minimum:
                            - at least two distinct XML namespaces on elements and/or
                              attributes (e.g. an SRU envelope namespace plus a MARCXML
                              or Dublin Core record namespace)
                            - a repeated element that appears exactly once in at least
                              one record and 2+ times in another, in the same document
                              or across two sample documents — this is the single-vs-list
                              ambiguity requirement.md FR4 and plan.md §4(b) name as XML's
                              main source of subtle bugs (JSON has no equivalent case)
                            - at least one element carrying a meaningful attribute (not
                              just a namespace declaration)
                          Save under this phase's own scratch area, not any production
                          path: docs/features/001-xml-response-support/phases/phase-1/spike/sample.xml
                          (create the spike/ subdirectory).
Why This Matters:         An unrepresentative sample (e.g. no repeated elements, no
                          attributes) would let this spike falsely validate a convention
                          that breaks on the first real SRU response Phase 4 tests against.
Dependencies:             None
Inputs/Preconditions:     None — no existing XML sample exists in this repo (confirmed:
                          the only XML in the codebase is a 12-byte `<root/>` stub in
                          backend/tests/test_connection_test_service.py:380, not usable
                          as a realistic sample).
Output/Artifact:          docs/features/001-xml-response-support/phases/phase-1/spike/sample.xml
                          — verifiable by inspection against the three required
                          characteristics above.
Placeholders:             None
Decision Type:            [REVERSIBLE] — a throwaway artifact; can be replaced with a
                          better sample later at zero cost if Phase 4's real e2e run
                          surfaces a shape this sample didn't cover (plan.md §12 Risk).
Security & Observability: N/A — throwaway local file, not committed application data;
                          no credentials or PII involved in the sample XML itself.
Testing Notes:            Not applicable — this task produces a fixture, not code.
                          Verification is visual inspection against the three required
                          characteristics listed in the Description.
```

```
Task ID:                  P1.A-02
Title:                    Trial a candidate XXE-safe parser against the sample
Description:              Write a throwaway script (same spike/ directory, e.g.
                          spike/trial.py — not a pytest file, not production code) that
                          parses sample.xml (P1.A-01) using a candidate XXE-safe
                          approach and dumps the raw, unnormalized output shape (print or
                          write to spike/raw_output.txt). Trial at least one of the two
                          candidates decisions.md DEC-2 names: (a) `defusedxml`'s
                          ElementTree-compatible walk (stdlib `xml.etree.ElementTree`-like
                          API, XXE-safe by construction) or (b) `xmltodict` layered over
                          a defused parser (`xmltodict.parse(..., expat=defusedexpat...)`
                          or equivalent — `xmltodict` alone is not XXE-safe; do not trial
                          it without a defused parser). `defusedxml` is not yet in
                          requirements.txt or requirements-dev.txt (confirmed via grep —
                          no XML library exists anywhere in the codebase today, matching
                          decisions.md DEC-2's context) — install it into the existing
                          backend venv for this trial only; do not edit requirements.txt
                          in this phase (that's Phase 2's P2.A, once the choice is final).
                          Observe: does the candidate's native output already resemble a
                          walkable dict/list, or does it require a manual ElementTree walk
                          to produce one? Record this observation for P1.B-04.
Why This Matters:         If the chosen library's native output shape needs substantial
                          manual conversion work, that effort belongs in Phase 2's module
                          design — better to discover it now than mid-Phase-2.
Dependencies:             P1.A-01 (sample.xml must exist)
Inputs/Preconditions:     sample.xml (produced by P1.A-01); backend venv (confirmed,
                          backend/.venv per repo layout) with the trialed library
                          pip-installed ad hoc.
Output/Artifact:          spike/trial.py plus its raw output dump (spike/raw_output.txt
                          or equivalent) — verifiable by running the script and visually
                          confirming it produced SOME structured (even if not yet
                          normalized) representation of sample.xml with no XXE-related
                          warnings/errors.
Placeholders:             None
Decision Type:            [REVERSIBLE] — adopts a new dependency (decisions.md DEC-2
                          already approved an XXE-safe library in principle); the exact
                          package is swappable in Phase 2 without affecting any other
                          phase, per DEC-2's stated reversibility.
Security & Observability: The entire point of this task is XXE safety (NFR1) — confirm
                          the candidate rejects or safely ignores a DOCTYPE/external-entity
                          declaration if you add one to a copy of the sample for this
                          check (do not skip this — a candidate that silently resolves
                          external entities fails NFR1 regardless of how clean its output
                          shape is). Do not log the sample content NOR the trial output
                          verbatim in anything meant to persist beyond this throwaway run.
Testing Notes:            Manual: run the script, inspect output. Explicitly try one
                          malicious-shaped input (a copy of sample.xml with an
                          `<!ENTITY>`/external-DOCTYPE injected) and confirm the candidate
                          either raises or strips it rather than resolving it — this is
                          the one property that must hold before P1.B proceeds.
```

### P1.B — Convention Validation

Objective: Apply the normalization convention (namespace-stripping, single-vs-list coercion, attribute/text handling) to the trial output from P1.A, then confirm — by calling the actual unmodified production functions, not reimplementations — that dot-notation record-root resolution and a schema-inference-style flatten both work against the result.
Deliverables: a normalized dict/list dump; confirmation that `extract_records_at_path` and `SchemaInferenceEngine._walk_record` produce sane output against it; `spike-findings.md` documenting the go/no-go decision and confirmed conventions.
Complexity/risk: low-medium — the flatten check (P1.B-03) needs a live Django settings context (see Inputs/Preconditions), which is the one place this spike can silently produce a false pass/fail if run wrong.

```
Task ID:                  P1.B-01
Title:                    Apply namespace-stripping, list-coercion, and attribute/text
                          conventions to the trial output
Description:              Extend spike/trial.py (P1.A-02) with a normalization pass over
                          the raw parsed output that: (a) strips XML namespace prefixes
                          from every element and attribute name before it becomes a dict
                          key (decisions.md DEC-5 — e.g. `srw:record` → `record`); (b)
                          coerces both a single occurrence and multiple occurrences of the
                          same repeated element into a list, consistently, so a
                          data_root_path-style path resolves identically regardless of
                          how many times that element occurred in this particular
                          response (requirement.md FR4) — use the sample's repeated
                          element from P1.A-01 to prove this concretely: show the
                          single-occurrence case and the multi-occurrence case both
                          produce a Python `list` at the same dot-notation path; (c)
                          decide and apply ONE convention for element attributes and text
                          content (e.g. `@attr` / `#text` keys, or an alternative) based
                          on what the P1.A-01 sample's attribute-bearing element actually
                          needs to preserve meaningfully — do not silently drop attribute
                          data (requirement.md §10 `[ASSUMPTION]`). Record the exact
                          convention chosen for P1.B-04.
Why This Matters:         Getting the single-vs-list coercion wrong is, per plan.md §4,
                          the main source of subtle bugs in this feature — a data_root_path
                          that resolves to a list on one page and a bare dict on another
                          would silently corrupt pagination record counts downstream.
Dependencies:             P1.A-02
Inputs/Preconditions:     spike/trial.py with raw output (P1.A-02, confirmed).
Output/Artifact:          spike/trial.py updated to emit a normalized dict/list —
                          verifiable by printing/dumping the normalized structure and
                          visually confirming: no namespace prefixes remain in any key;
                          the repeated element resolves to a list in both the
                          single-occurrence and multi-occurrence cases; attribute/text
                          values are present under the chosen convention, not dropped.
Placeholders:             None
Decision Type:            [REVERSIBLE] — the attribute/text convention and coercion rule
                          are this phase's confirmed output, feeding Phase 2's production
                          module; either can be revised via a Phase 1 addendum (plan.md
                          §10 `[VOLATILE]` note) without touching Phase 3/4.
Security & Observability: N/A — same throwaway-script scope as P1.A-02; no new library
                          or network call introduced here, purely data transformation.
Testing Notes:            Manual: dump normalized output before/after for the
                          single-occurrence vs. multi-occurrence repeated-element case
                          side by side and confirm both are lists. Edge case to note (not
                          necessarily solve): what happens to mixed content (an element
                          with both text and child elements) — observe the candidate's
                          behavior and record it in spike-findings.md as a known
                          limitation if the sample happens to contain any, per plan.md
                          §12's residual-risk note; do not block go/no-go on this unless
                          the target sample actually requires it.
```

```
Task ID:                  P1.B-02
Title:                    Validate dot-notation record-root resolution against the
                          normalized output  [P]
Description:              Using the ACTUAL, unmodified `extract_records_at_path` function
                          (backend/api_connector/services/pagination/utils.py:16 —
                          `extract_records_at_path(data: dict | list, path: str | None) -> list`,
                          confirmed current signature), call it directly from spike/trial.py
                          against the normalized output from P1.B-01, passing a
                          dot-notation path string pointing at the sample's record root
                          (the same convention `Endpoint.data_root_path` uses today for
                          JSON, e.g. `"searchRetrieveResponse.records"`). Do NOT
                          reimplement or approximate this function — import and call the
                          real one, per this breakdown's Rule 1 (build against actual
                          code). Confirm it returns the expected list of record dicts, not
                          an empty list (which extract_records_at_path returns silently on
                          any failure — a false "it works" reading is possible if the path
                          string is simply wrong, not if normalization is wrong; check the
                          returned list's contents, not just its non-emptiness).
Why This Matters:         This is the crux of Requirement §3's riskiest assumption for the
                          pagination-fetch side: if the real, unmodified function can't
                          resolve a normalized-XML record root, the single-chokepoint
                          design (decisions.md DEC-1) doesn't hold and Phase 2-4 need
                          bespoke XML-aware traversal instead.
Dependencies:             P1.B-01
Inputs/Preconditions:     Normalized output from P1.B-01 (confirmed);
                          backend/api_connector/services/pagination/utils.py (confirmed
                          present, no Django settings dependency — this function has no
                          django imports, so it runs under plain `python`, no manage.py
                          shell needed).
Output/Artifact:          A recorded result (console output or a short note) showing the
                          exact dot-notation path string used and the list of records it
                          resolved — verifiable by inspection: the returned list's length
                          and first-record shape match the normalized sample.
Placeholders:             None
Decision Type:            None — this task validates an existing, unmodified function;
                          no design choice is made here.
Security & Observability: N/A — calling a pure function with no side effects, no
                          credentials or network I/O involved.
Testing Notes:            Manual: confirm both a correct path (resolves records) and a
                          deliberately wrong path (confirm it returns `[]`, matching the
                          function's documented "never raises, returns [] on failure"
                          contract) — this distinguishes "normalization is broken" from
                          "I typed the wrong path."
```

```
Task ID:                  P1.B-03
Title:                    Validate schema-inference-style flatten against the normalized
                          output  [P]
Description:              Using the ACTUAL, unmodified `SchemaInferenceEngine._walk_record`
                          method (backend/api_connector/services/schema_inference/engine.py:107
                          — `_walk_record(self, obj: dict, prefix: str, depth: int) -> dict[str, Any]`,
                          confirmed current signature), instantiate `SchemaInferenceEngine()`
                          (engine.py:97) and call `_walk_record` directly against one or
                          more records from the list resolved in P1.B-02. Do NOT
                          reimplement this method — call the real one (Rule 1). Confirm
                          the resulting flat `{dot.path: value}` map has: no two distinct
                          source elements (e.g. two same-named elements that came from
                          different original namespaces, if the sample has any) colliding
                          on the same key with different meanings; sane, human-readable
                          paths a user could plausibly configure a `SchemaField` against
                          (requirement.md §5 SC4's eventual bar, though SC4 itself belongs
                          to Phase 3). Run this from `python manage.py shell` (or a script
                          invoked through it) from backend/ — NOT bare `python -c` or a
                          standalone interpreter: `SchemaInferenceEngine.__init__` reads
                          `settings.SCHEMA_INFERENCE_MAX_DEPTH` via `django.conf.settings`
                          (engine.py:105, default 10, `config/settings.py:117`), which
                          raises `ImproperlyConfigured` outside a Django context — running
                          this bare would make an import/config error look like a logic
                          failure in the flatten itself.
Why This Matters:         This is the crux of Requirement §3's riskiest assumption for the
                          schema-inference side: colliding field paths from
                          different-namespace same-named elements would produce a corrupt
                          or misleading field list for the user, and mixed content
                          wouldn't flatten sanely — either would mean Phase 3 needs
                          bespoke XML handling in `_walk_record`, contradicting FR5's
                          zero-code-change bet.
Dependencies:             P1.B-02
Inputs/Preconditions:     Normalized records (P1.B-01/02, confirmed); Django app
                          importable via `python manage.py shell` from backend/
                          (confirmed, backend/manage.py exists); no database access
                          needed — `_walk_record` takes a plain dict and has no DB calls.
Output/Artifact:          A recorded flat path→value map for at least one normalized
                          record — verifiable by inspection: every key is a clean
                          dot-notation path with no namespace prefixes, no two keys
                          collide with contradictory meanings, and the repeated element
                          from P1.A-01 shows the correct sentinel/child-path behavior
                          `_walk_record`'s existing docstring describes (ARRAY_OF_OBJECTS
                          sentinel + recursion into the first item).
Placeholders:             None
Decision Type:            None — validates an existing, unmodified method; no design
                          choice is made here.
Security & Observability: N/A — `_walk_record` has no side effects and makes no external
                          calls; do not print/persist actual field values beyond this
                          throwaway run if the sample happens to resemble real records
                          with sensitive-looking data.
Testing Notes:            Manual: inspect the flattened map for (a) zero namespace-prefix
                          leakage in any key, (b) zero key collisions with differing
                          value shapes, (c) the repeated element appearing correctly as
                          the ARRAY_OF_OBJECTS_SENTINEL path plus child paths, matching
                          the same behavior an equivalent JSON body would produce.
```

```
Task ID:                  P1.B-04
Title:                    Write spike-findings.md — go/no-go decision and confirmed
                          conventions
Description:              Write
                          docs/features/001-xml-response-support/phases/phase-1/spike-findings.md
                          summarizing: (1) the library chosen (P1.A-02) and why, versus
                          the untrialed alternative; (2) the confirmed namespace-stripping
                          rule (P1.B-01); (3) the confirmed single-vs-list coercion rule
                          (P1.B-01), with the concrete before/after example from the
                          sample; (4) the confirmed attribute/text-content key convention
                          (P1.B-01), with the concrete example; (5) the P1.B-02 and P1.B-03
                          results (pass/fail on real-function resolution and flatten); (6)
                          any observed limitation not fully resolved (e.g. mixed content
                          behavior, namespace-collision edge case) as a named residual
                          risk, cross-referenced to plan.md §12; (7) the go/no-go verdict
                          per plan.md §6's gate definition. This is the artifact Phase 2's
                          breakdown will read as its primary confirmed-reality input —
                          write it as that audience, not as a lab notebook.
Why This Matters:         Without this note, Phase 2's Breakdown Engineer invocation has
                          no durable record of what this phase actually confirmed and
                          would have to re-derive the convention from scratch or guess —
                          defeating the entire purpose of a spike phase preceding
                          production work.
Dependencies:             P1.B-01, P1.B-02, P1.B-03
Inputs/Preconditions:     Results from P1.A-02, P1.B-01, P1.B-02, P1.B-03 (confirmed, all
                          prior tasks in this phase).
Output/Artifact:          docs/features/001-xml-response-support/phases/phase-1/spike-findings.md
                          — verifiable by a human reading it and confirming all 7 items
                          in the Description are present and each cites a concrete
                          observation from this phase's trial, not a restated assumption
                          from requirement.md.
Placeholders:             None
Decision Type:            [REVERSIBLE] — a documentation artifact; if the human review
                          disagrees with the go/no-go read on the same evidence, this file
                          is edited directly (Mode: REVISE) with no code to unwind.
Security & Observability: Do not include full sample record contents or credentials in
                          this file if the real captured SRU sample (P1.A-01) happens to
                          contain anything sensitive-looking — reference field shapes and
                          short excerpts only, consistent with the project's "never log
                          full response bodies" convention (project-detail.md §7 Logging).
Testing Notes:            Not applicable — this task produces documentation. Verification
                          is the human review checklist in §4 below.
```

---

## 4. Phase Acceptance Criteria & Verification

**Completion criteria** (falsifiable; traces to Requirement §3 Riskiest Assumption — this whole phase exists to test it; no `requirement.md` §5 Success Criterion is individually owned by Phase 1, per plan.md §7's Phase Overview, but a "no-go" result here would invalidate the feasibility of SC2-SC6 before any of them are built):

- WHEN a representative namespaced XML sample (P1.A-01) is run through the trialed candidate library and the P1.B-01 normalization convention, the system SHALL produce a `dict`/`list` structure containing no XML namespace prefixes in any key.
- WHEN the unmodified `extract_records_at_path` (P1.B-02) is called against that normalized structure with a `data_root_path`-style dot-notation string, it SHALL return the expected list of record dicts (non-empty, correct shape) — not merely a non-empty list, but the actual expected records.
- WHEN the unmodified `SchemaInferenceEngine._walk_record` (P1.B-03) is called against a normalized record, it SHALL produce a flat path→value map with zero colliding keys carrying contradictory meanings.
- `spike-findings.md` (P1.B-04) SHALL exist and state an explicit go/no-go verdict per plan.md §6's gate, plus the four confirmed-convention items listed in P1.B-04's Description.

**Manual verification steps** (human smoke test):

1. Open `spike/sample.xml` — confirm it visibly contains 2+ namespaces, a repeated element with a provable single/multi split, and at least one meaningful attribute.
2. Open `spike-findings.md` — confirm all 7 items from P1.B-04 are present and each references a concrete result from this phase (not a restated requirement/assumption).
3. Re-run `spike/trial.py` locally (bare `python` is fine up through the P1.B-01 normalization step; the `_walk_record` check must go through `python manage.py shell` per P1.B-03) and confirm the console output matches what `spike-findings.md` claims.
4. Confirm no edits were made to any production file (`engine.py`, `utils.py`, `schema_inference/engine.py`, `requirements.txt`, migrations) — this phase is scoped to `docs/features/001-xml-response-support/phases/phase-1/` only.

**Expected automated coverage**: None. This is throwaway spike code, not production code (Rule 2; plan.md §7 Phase 1 Artifacts) — no pytest file, no CI change, no fixture committed to `backend/tests/`. If `spike-findings.md`'s go verdict holds, Phase 2's own breakdown will specify the first real automated tests against the production XML module; this phase intentionally produces none.

---

## 5. Handoff Note

Build against commit `44a191c` on branch `001-xml-response-support`. No `[REVIEW-GATE]` subphases in this phase. No `[IRREVERSIBLE]` tasks. No Open Decisions block the start of this phase (§2 explains why the two candidate ambiguities are this phase's own deliverable, not a pre-implementation gate).

**Before Phase 2's breakdown is generated**: a human must review `spike-findings.md` and, if the go verdict is accepted, append its confirmed library/convention choices to `decisions.md` as `DEC-8` (Origin: Breakdown Engineer · Phase 1 · REVISE) — Phase 2's own breakdown will cite `DEC-8` as its precedent for the production module's design, per this pipeline's JIT convention (§ WHY JUST-IN-TIME).

The implementor writes the throwaway trial code and `spike-findings.md` and commits **nothing** — the human reviews, edits, and commits.
