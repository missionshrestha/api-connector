# XML Response Support — Decision Log

Feature ref: `001-xml-response-support` · Created: 2026-07-23

---

**DEC-1: Normalize XML at the single existing pagination chokepoint, not throughout the pipeline**
Context: Every JSON-shape-aware function in the pipeline (`extract_records_at_path`, all 6 pagination strategies, `SchemaInferenceEngine._walk_record`, `DataPreviewService`) already operates purely on Python `dict`/`list`, downstream of one `response.json()` call in `PaginationEngine.paginate()` (`engine.py:146`).
Options: (a) teach every one of those functions to also understand XML natively; (b) convert XML → the same `dict`/`list` shape at the single existing parse call site, leaving everything downstream untouched.
Decision: (b) — normalize at the chokepoint.
Rationale: Smallest reviewable surface; adapt over disrupt — the codebase already centralized JSON parsing to one line, which is exactly what makes this cheap. Multiplying XML-awareness into 8+ separate functions would add risk and maintenance surface for no benefit over a single conversion function.
Reversibility: [REVERSIBLE] — if the Technical Spike (Phase 1) finds this doesn't hold for real XML shapes, the design reverts to option (a) for the specific layers that need it, without having built anything throwaway beyond the spike itself.
Status: Decided.

**DEC-2: New XXE-safe XML library is additive, not a replacement of an existing pattern**
Context: No XML library exists anywhere in the codebase today (`requirements.txt`/`requirements-dev.txt` confirmed clean); no XXE-safety precedent exists either, unlike SSRF, which has a dedicated module and default-off/configurable posture.
Options: (a) raw `xml.etree.ElementTree` (stdlib, no new dependency, XXE-unsafe by default in the general case); (b) `defusedxml` or equivalent XXE-safe wrapper (new dependency, safe by default).
Decision: (b), pending final confirmation of the specific library in Phase 1's spike.
Rationale: Security priority (Decision Priority Order: Business value → Correctness → **Security** → ...) and the project's existing security-conscious posture (dedicated SSRF module, completed security audit) argue for safe-by-default XML parsing even though no XML precedent exists to adapt to. This is not a "replace an existing pattern" call — there's nothing to replace — but the library choice itself was surfaced to the human given its new-dependency and security implications.
Reversibility: [REVERSIBLE] — swapping the specific XXE-safe library in Phase 2 doesn't affect any other phase, since only the parsing module's internals change.
Status: Decided (approach); specific library deferred to Phase 1.

**DEC-3: `Endpoint.response_format` is a `TextChoices` field, not free text**
Context: `ConnectionProfile.last_test_detected_format` (the only existing format-related field) is a free-text `CharField`, not tied to any enum. All other enums in the codebase follow `TextChoices` (ADR-003).
Options: (a) mirror `last_test_detected_format`'s free-text pattern for consistency with the one existing format field; (b) follow the project-wide `TextChoices` convention (ADR-003).
Decision: (b).
Rationale: ADR-003 is a project-wide, explicitly documented convention for all enums; `last_test_detected_format`'s free-text shape is a display-only field with no downstream consumer, not a precedent to extend into a field that now drives real branching logic (`PaginationEngine`'s format dispatch).
Reversibility: [REVERSIBLE] — field type is set at migration time; changing it later is a standard migration, not an architectural change.
Status: Decided.

**DEC-4: Format routing via a persisted `Endpoint.response_format` field, not per-request re-detection**
Context: Two options for how `PaginationEngine` knows which parser to use for a given endpoint: re-sniff Content-Type/body on every paginated request (like the connection-test diagnostic already does once), or read a persisted, user-editable field.
Options: (a) re-sniff every page fetch — no new model field/migration, but adds per-page overhead and risks inconsistent behavior if an API's error responses have a different content-type than its success responses mid-pagination; (b) persisted `Endpoint.response_format`, defaulted from the connection test's already-computed `last_test_detected_format`, user-overridable.
Decision: (b).
Rationale: Matches the existing precedent that endpoint-level persisted config drives fetch behavior (`data_root_path`, `PaginationConfig`'s strategy/limits are all persisted, not re-detected per request). Also closes a real gap the codebase survey found: format detection is already computed and stored during connection test but currently has zero downstream consumers — wiring it to default this new field reuses that existing computation rather than duplicating it.
Reversibility: [REVERSIBLE] — the field can be removed in favor of re-detection later, though it would be a behavior change users would notice (loses the ability to manually override a misdetected format).
Status: Decided. Confirmed with human via `AskUserQuestion` during Requirement Architect convergence, 2026-07-23.

**DEC-5: Dot-notation paths strip XML namespaces by default**
Context: XML documents in the target use case (SRU/MARCXML-style public-data APIs) commonly namespace elements (e.g. `<srw:record><dc:title>`). The existing dot-notation convention (`data_root_path`, `key_path`, etc.) has no namespace concept, since JSON has no namespaces.
Options: (a) strip namespace prefixes by default, so paths stay as simple as `"record.title"`; (b) preserve full namespaced tag names, requiring paths like `"srw:record.dc:title"`.
Decision: (a).
Rationale: Matches the simplicity of the existing JSON dot-path UX exactly; same-named elements colliding across different namespaces is treated as an acceptable rare edge case for MVP scope, versus forcing every user to know and type XML namespace prefixes for basic configuration.
Reversibility: [REVERSIBLE] — could add opt-in namespace-preserving mode later without breaking existing namespace-stripped configs, since it would be an additive path-resolution option.
Status: Decided. Confirmed with human via `AskUserQuestion` during Requirement Architect convergence, 2026-07-23.

**DEC-6: "Raw Response" preview shows original XML text, not a JSON reinterpretation**
Context: `DataPreviewService` currently always re-serializes the parsed response body as JSON for the raw-response preview panel (`data_preview.py:206`, `raw_response_body = json.dumps(last_raw_body, ...)`), regardless of what the source API actually returned.
Options: (a) keep re-serializing everything as JSON, including XML-derived data — simpler, no new code path; (b) preserve and show the original XML text for XML-format endpoints.
Decision: (b).
Rationale: "Raw response" should mean what the API actually returned. Showing a JSON reinterpretation of an XML response would misrepresent the real payload to a user debugging against the source API's actual documented shape.
Reversibility: [REVERSIBLE] — a display-layer change with no effect on stored data or downstream schema/pagination logic.
Status: Decided. Confirmed with human via `AskUserQuestion` during Requirement Architect convergence, 2026-07-23.

**DEC-7: `record_count_path` runtime consumption is out of scope**
Context: Codebase survey found `Endpoint.record_count_path` is persisted and serializer-validated but never consumed by any backend service (`PaginationEngine`, `SchemaInferenceEngine`, `DataPreviewService`) — for JSON endpoints today, not just XML.
Options: (a) wire up runtime consumption of `record_count_path` as part of this feature, achieving a "better than JSON" state for XML; (b) leave it at parity with current JSON behavior (persisted, unconsumed) and treat wiring it up as a separate, pre-existing gap.
Decision: (b).
Rationale: Smallest reviewable surface — this feature's mandate is XML reaching parity with existing JSON behavior, not fixing unrelated pre-existing gaps that happen to be adjacent. Fixing `record_count_path` consumption is a legitimate future task but is out of scope here.
Reversibility: [REVERSIBLE] — can be picked up as its own feature/task at any time, independent of this one.
Status: Decided.

---

**Implementor tactical decisions — Phase 1 (Origin: Implementor · Phase 1 · 2026-07-23)**

These are tactical implementation-level decisions made while executing Phase 1's breakdown, distinct from the formal `DEC-8` promotion the breakdown's Handoff Note reserves for a human/Breakdown Engineer step after reviewing `spike-findings.md`. Full detail in `phases/phase-1/spike-findings.md`.

- **[SUPERSEDED — see below] ~~Candidate library trialed: `defusedxml.ElementTree` (not `xmltodict`)~~.** Originally decided without trialing `xmltodict`; at the human's request both were subsequently trialed in full (research + a 5-sample practical trial). See the "Deepened library comparison" entry below for the revised recommendation.
- **List-coercion algorithm: two-pass, scoped by `(parent_tag, child_tag)` pair, not a flat per-tag-name count.** A naive "wrap every child in a list unconditionally" approach was tried first and found to break `extract_records_at_path`'s dict-only intermediate-segment traversal (a singular container like `<records>` becoming a 1-item list broke the next `.get()` call). A flat, non-parent-scoped occurrence count was tried second and found to over-generalize (a tag appearing once per record but across multiple records was wrongly flagged repeatable). The `(parent_tag, child_tag)`-scoped, max-count-anywhere-in-document heuristic is the confirmed convention — see `spike-findings.md` §3 for the full before/after proof. This is the one piece of real algorithmic complexity Phase 2 must port faithfully, and it was independently re-implemented (via `xmltodict`'s native `force_list` callable) and produced identical results — see the deepened comparison below.
- **Attribute/text convention: `@attr`/`#text`, with a pure-text-leaf collapse optimization** (a leaf with no attributes/children collapses directly to its text value, not `{"#text": "..."}`) — matches the common case's shape to what a JSON API would produce. See `spike-findings.md` §4. **Refined**: the initial `ElementTree` implementation only captured an element's leading text (`elem.text`), silently dropping text following child elements (`child.tail`) — a real bug, found via the deepened comparison's mixed-content sample and fixed (concatenate `elem.text` + every `child.tail`, matching `xmltodict`'s own semantics exactly). Phase 2 must handle both, not just `elem.text`, if it ports the `ElementTree` approach.
- **Sample sourced from a real, live SRU endpoint** (Deutsche Nationalbibliothek, `services.dnb.de/sru/dnb`) rather than hand-authored, per plan.md §6's stated preference — confirmed network access was available in this environment; no credentials or SSRF-relevant code path involved (a one-off `curl`, not `BaseHTTPClient`).

**Deepened library comparison — Origin: Implementor · Phase 1 · 2026-07-23 (at human request, after the initial spike)**

Both `decisions.md` DEC-2 candidates were trialed in full — research (maintenance/security posture) plus a practical trial against 5 samples (2 real: the original DNB sample + a 2nd real MARCXML source from Library of Congress; 3 synthetic: mixed content, a namespace collision, and a ~3.1MB/5000-record performance case). Full detail and evidence in `spike-findings.md` §8.

- **`defusedxml` is dormant** (0.7.1 since 2021; an unreleased `0.8.0rc2` has sat on PyPI since 2023) but still the Python core team's stated recommendation as of a September 2023 discussion, since it documents/guarantees a safety posture the stdlib provides only as an undocumented implementation detail.
- **The breakdown's named companion package for the `xmltodict` candidate, `defusedexpat`, is dead** (last released 2013, Python 3.3/3.4 only, incompatible with this project's Python 3.11+/3.12). This was an incorrect assumption baked into DEC-2/the breakdown at the time they were written — not knowable without this research pass.
- **Modern `xmltodict` (1.0.4, actively maintained) has a built-in `disable_entities=True` default** that independently blocks entity declarations (both classic XXE and billion-laughs), verified empirically — a materially different security picture than DEC-2's original assumption that "xmltodict alone is not XXE-safe."
- **Empirically, both candidates are equally safe by default** against classic XXE and billion-laughs attacks on this project's Python version; neither forbids a bare `DOCTYPE` with no entity by default either (a shared, not differentiating, limitation). A ~20-line hand-written hardened-expat shim (reusing `defusedxml.common`'s own exception classes) closes this gap for either candidate if a team wants it.
- **Once one real bug was fixed (see the mixed-content note above), both candidates produced byte-identical normalized output across all 5 samples**, and both independently validated against the real, unmodified `extract_records_at_path` and `SchemaInferenceEngine._walk_record`.
- **Performance**: `xmltodict` is ~1.7x slower than `ElementTree` at a deliberately large stress size (5000 records/~3.1MB); likely immaterial at real SRU page sizes (tens of records), but not yet confirmed against the actual target API.
- **Recommendation: `xmltodict`**, weighing Reliability (active maintenance) and Maintainability (materially less custom code, and it didn't have the bug the `ElementTree` path did) as the deciding factors, since Security is a tie at default settings today. This is not a unanimous call across every axis (`ElementTree` wins on raw performance) — see `spike-findings.md` §8.5 for the full weighted breakdown. Either choice remains reversible per DEC-2.

---

**DEC-8: Phase 1's confirmed XML normalization convention and library choice, promoted for Phase 2**
Context: `decisions.md` DEC-2 deferred the exact XXE-safe library to Phase 1's spike; `requirement.md` §10 deferred the attribute/text-content key convention to the same spike. Phase 1's spike (`phases/phase-1/spike-findings.md`) and its deepened library comparison (§8, and the "Deepened library comparison" entry above) resolved both empirically, and Reconciler independently re-ran the full trial (both candidates, all 5 samples, the security payloads, and a fresh `pip-audit`) and confirmed every claim before this promotion — see `phases/phase-1/reconciliation.md`.
Decision: Phase 2 builds the production XML parsing module against the following, confirmed by trial-and-observation, not assumed:
  - **Library: `xmltodict`** (not `defusedxml.ElementTree`, the original tentative DEC-2 lean). `defusedexpat` — DEC-2's assumed companion package for the `xmltodict` candidate — is dead (Python 3.3/3.4-only) and must not be depended on. If `forbid_dtd`-level hardening beyond `xmltodict`'s own `disable_entities=True` default is wanted, the ~20-line hardened-expat shim in `phases/phase-1/spike/trial_xmltodict.py`'s `_HardenedExpatModule` is the viable path instead, reusing `defusedxml.common`'s exception classes.
  - **Namespace stripping**: every element/attribute tag reduced from Clark notation (`{uri}localname`) to `localname` via a single regex, before it becomes a dict key.
  - **List coercion**: a two-pass algorithm scoped by `(parent_tag, child_tag)` pair — Pass 1 records, per pair, the maximum occurrence count under any single instance of `parent_tag` anywhere in the document; Pass 2 coerces a child to a list if it repeats locally OR its pair is in that repeatable set. A naive flat-count or unconditional-list rule is proven broken (see `spike-findings.md` §3) and must not be used.
  - **Attribute/text convention**: `@attr`/`#text` keys, with a pure-text-leaf collapse (a leaf with no attributes/children collapses to its text value, not a wrapper dict). Text content for a mixed-content element must concatenate `elem.text` + every child's `.tail` if the `ElementTree` approach is ever used instead of `xmltodict` (`xmltodict` handles this natively).
Rationale: Decision Priority Order — Security is a tie between both candidates at default settings on this project's Python version (contrary to DEC-2's original framing); Reliability (active maintenance) and Maintainability (materially less custom code, and `xmltodict` avoided the mixed-content bug the `ElementTree` path had) are the deciding factors. `ElementTree` remains ~1.7x faster at a synthetic 5000-record stress size — not yet confirmed to matter at real SRU page sizes; Phase 2 should benchmark against the actual target API before treating this as settled.
Reversibility: [REVERSIBLE] — matches DEC-2's own reversibility note; swapping the library later touches only the parsing module's internals.
Residual risks carried forward (not resolved by this decision, tracked for Phase 2+): cross-namespace same-local-name key collision (DEC-5's already-accepted risk, concretely demonstrated in this phase); the `(parent_tag, child_tag)` heuristic is document-local, not schema-aware — a field repeating exactly once on every record of some future page, with no other same-page evidence of repetition, could resolve as a scalar instead of a list.
Status: Decided. Origin: Breakdown Engineer · Phase 1 · REVISE — promoted from `spike-findings.md`'s confirmed findings, per breakdown.md's Handoff Note, following Reconciler's independent re-verification (`phases/phase-1/reconciliation.md`).
