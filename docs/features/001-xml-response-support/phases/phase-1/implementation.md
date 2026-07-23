HEADER
  Feature 001-xml-response-support · Phase 1 — Technical Spike: XML Normalization Feasibility
  Baseline commit: 44a191cfc289a9b10308960bf3c545f6b52fe0f7 on branch 001-xml-response-support
  State: UNCOMMITTED working tree (review with: git diff 44a191c)
  Status: READY FOR REVIEW

---

## 1. Summary

Ran the Phase 1 technical spike to de-risk the plan's core bet: that normalizing real-world namespaced XML into the same dict/list convention `response.json()` produces lets the existing pipeline (`extract_records_at_path`, `SchemaInferenceEngine._walk_record`) work unmodified. Fetched a real, live SRU response from Deutsche Nationalbibliothek's public SRU API as the sample, trialed `defusedxml.ElementTree`, and iterated the normalization convention through two failed attempts before landing on a working one — a naive "wrap every element in a list" approach broke path traversal, and a naive "flat tag-name count" approach over-generalized. The confirmed convention (namespace-stripping, a `(parent_tag, child_tag)`-scoped two-pass list-coercion algorithm, and an `@attr`/`#text` attribute convention) was validated end-to-end against the real, unmodified `extract_records_at_path` and `SchemaInferenceEngine._walk_record`. **Verdict: GO.**

**Extended at the human's request**: both `decisions.md` DEC-2 candidates (`defusedxml.ElementTree` and `xmltodict`) were then trialed in full — in-depth research plus a practical trial against 5 samples (2 real, 3 synthetic edge cases: mixed content, a namespace collision, and a performance stress case). This surfaced two material findings: (1) the breakdown's assumed companion package for the `xmltodict` path, `defusedexpat`, is dead and incompatible with this project's Python version; (2) a real bug in the `ElementTree` implementation (silently dropping text after child elements in mixed content) that only surfaced once tested against a genuine mixed-content sample — fixed during this session. Once fixed, both candidates produced byte-identical output across all 5 samples. Revised recommendation: **`xmltodict`**, on Reliability (active maintenance) and Maintainability (less custom code) grounds, since Security is now a tie at default settings on this project's Python version — full weighted reasoning in `spike-findings.md` §8.

No production code was touched at any point; everything here is throwaway spike code plus documentation, per this phase's scope.

## 2. What Changed — file by file

- `docs/features/001-xml-response-support/phases/phase-1/spike/sample.xml` (new): a real, unmodified captured response from `services.dnb.de/sru/dnb` (public SRU API), containing 6 distinct namespace declarations, a proven single-vs-multi occurrence case (`dc:creator`: 1/absent/2 across 3 records), and 12 meaningful `xsi:type` attributes.
- `docs/features/001-xml-response-support/phases/phase-1/spike/trial.py` (new, throwaway): the full trial script — raw parse observation (P1.A-02), XXE-rejection check, the normalization convention (P1.B-01), `extract_records_at_path` validation (P1.B-02, runs under bare `python`), and `SchemaInferenceEngine._walk_record` validation (P1.B-03, must run via `python manage.py shell`). Extensive inline comments record the two failed convention attempts and why each failed — this is deliberate; it's the load-bearing part of the record for Phase 2 to read.
- `docs/features/001-xml-response-support/phases/phase-1/spike/raw_output.txt` (new): full console dump of the raw parse + normalized structure + `extract_records_at_path` result, for the human's "re-run and confirm it matches" verification step.
- `docs/features/001-xml-response-support/phases/phase-1/spike/walk_record_output.txt` (new): full flattened path→value maps from the `_walk_record` check.
- `docs/features/001-xml-response-support/phases/phase-1/spike-findings.md` (new, later extended): the go/no-go writeup — library choice, confirmed conventions (with before/after proof), P1.B-02/03 results, residual risks, verdict, plus a new §8 deepened library comparison.
- `docs/features/001-xml-response-support/decisions.md` (appended, later extended): tactical Implementor decisions for Phase 1 (library choice, coercion algorithm, attribute convention, sample provenance), plus a "Deepened library comparison" entry — distinct from the formal `DEC-8` promotion the breakdown reserves for the human/Breakdown Engineer step.
- `docs/_meta/active-context.md` (updated): Phase 1 status → "Ready for review"; Next Action updated to point at this file and the `DEC-8` promotion step.

**Added for the deepened comparison** (at the human's request, after the initial spike above was already complete):
- `docs/features/001-xml-response-support/phases/phase-1/spike/trial_xmltodict.py` (new, throwaway): the `xmltodict`-based counterpart to `trial.py` — same normalization convention, built on `xmltodict`'s native `force_list` callable + `postprocessor` mechanisms instead of a hand-rolled tree walk; includes the XXE/billion-laughs/bare-DOCTYPE security trial (both at `xmltodict`'s own default `disable_entities=True` and against a hand-written hardened-expat shim, `_HardenedExpatModule`, since the breakdown's assumed `defusedexpat` companion package is dead); and a `compare_on_sample()` helper that runs both candidates side-by-side with timing.
- `docs/features/001-xml-response-support/phases/phase-1/spike/samples/sample_loc_marc.xml` (new): a 2nd real captured sample, from Library of Congress's public SRU/MARCXML endpoint — a differently-shaped real-world case (prefixed `zs:` namespace, `tag`/`ind1`/`ind2`/`code`-attribute-driven repeated elements).
- `docs/features/001-xml-response-support/phases/phase-1/spike/samples/sample_mixed_content.xml` (new, synthetic): constructed specifically to exercise mixed content, which neither real sample happened to contain — this is what surfaced the `ElementTree` bug described in §1.
- `docs/features/001-xml-response-support/phases/phase-1/spike/samples/sample_ns_collision.xml` (new, synthetic): constructed specifically to concretely demonstrate the cross-namespace key-collision risk DEC-5 already accepts as a known limitation.
- `docs/features/001-xml-response-support/phases/phase-1/spike/samples/sample_large.xml` (new, synthetic, ~3.1MB/5000 records, generated by a one-off script not preserved as a separate file): a stress-test case for timing comparison, well above real SRU per-page response sizes.
- `docs/features/001-xml-response-support/phases/phase-1/spike/raw_output_xmltodict.txt`, `walk_record_output_xmltodict.txt` (new): the `xmltodict` path's equivalent evidence trail to `raw_output.txt`/`walk_record_output.txt`.
- `docs/features/001-xml-response-support/phases/phase-1/spike/trial.py` (modified): fixed the mixed-content bug found via the practical trial (§5 below) — element text normalization now concatenates `elem.text` with every child's `.tail` text, matching `xmltodict`'s own semantics exactly (re-verified byte-identical afterward).

**No production file was touched, at any point** — no changes to `engine.py`, `utils.py`, `schema_inference/engine.py`, `requirements.txt`, or any migration.

## 3. How It Works

`trial.py` runs in two stages, matching the breakdown's task split:

1. **Bare `python` stage** (`trial_raw_parse` → `trial_xxe_rejection` → `trial_normalize` → `validate_extract_records_at_path`): parses `sample.xml` with `defusedxml.ElementTree`, confirms XXE rejection with an in-memory malicious payload, builds the normalized dict/list via a two-pass algorithm (Pass 1: `_collect_max_occurrence_counts` walks the tree once to find, per `(parent_tag, child_tag)` pair, the max occurrence count anywhere in the document; Pass 2: `element_to_normalized` builds the dict/list tree, coercing a child to a list when it repeats locally OR its pair is in the repeatable set), then calls the real `extract_records_at_path` against the result.
2. **`manage.py shell` stage** (`run_walk_record_check`): re-parses and re-normalizes independently (no shared state with stage 1, since it's a separate process), resolves the record list the same way, then calls the real `SchemaInferenceEngine()._walk_record` on each record and prints the flattened path→value maps.

The key design decision embedded in the normalization (§4 of `spike-findings.md`) is *why* a tag becomes a list: not "does it look like it repeats", but "does this exact `(parent_tag, child_tag)` pair's occurrence count exceed 1 anywhere in the document" — computed in a dedicated first pass before the tree is built, so the decision is available consistently to every occurrence of that pair, including ones where it only shows up once.

`trial_xmltodict.py` implements the identical convention, but via `xmltodict`'s own mechanisms rather than a hand-rolled walk: a `postprocessor` callback strips namespace prefixes (and drops `xmlns`/`xmlns:*` declaration keys, which `xmltodict` otherwise surfaces as regular attributes — an ElementTree/xmltodict difference worth knowing about), and a `force_list` callable implements the exact same `(parent_tag, child_tag)`-scoped two-pass algorithm — Pass 1 parses once with `force_list=True` (wrapping every child uniformly) purely to walk the result and compute the same max-occurrence-count table; Pass 2 is the real parse, using that table via the callable. `xmltodict` already natively provides the `@attr`/`#text` convention and automatic pure-text-leaf collapse, so those needed no custom code at all — a smaller implementation surface than the `ElementTree` path required.

## 4. Decisions Made

See `decisions.md`'s "Implementor tactical decisions — Phase 1" and "Deepened library comparison" sections for the full list with rationale. Weighed against the Decision Priority Order (Business value → Correctness → Security → Reliability → Scalability → Maintainability → Cost → Speed of implementation):

- The two failed coercion attempts (initial spike) were both **Correctness** failures (one broke traversal outright, the other silently produced wrong shapes for `title`) — surfaced and fixed within this phase rather than carried forward.
- **The library recommendation changed from the initial spike's tentative `defusedxml.ElementTree` call to `xmltodict`**, once both were actually trialed. The initial call was made without trialing `xmltodict` at all, reasoning speculatively that both would need equal custom code — the practical trial proved that assumption wrong (`xmltodict` needed materially less code, and its native mixed-content handling was correct where the hand-rolled `ElementTree` walk had a real bug). With **Security** now a tie at default settings (contrary to the original DEC-2 framing, since modern `xmltodict` has its own built-in entity-blocking and modern Python's stdlib expat already blocks external entities/billion-laughs by default), the deciding factors dropped to **Reliability** (active maintenance — `xmltodict` 1.0.4 vs. `defusedxml`'s dormant 0.7.1/unreleased 0.8.0rc2) and **Maintainability** (less custom code, demonstrated to matter by the bug found). **Scalability** favors `ElementTree` (~1.7x faster at stress-test size) but is judged unlikely to matter at real SRU page sizes — flagged for Phase 2 to confirm, not treated as settled.

## 5. Deviations from the Breakdown

- **[local]** The normalization convention went through two visibly-wrong intermediate attempts before landing on the confirmed one (see `trial.py`'s inline comments and `decisions.md`). This isn't a deviation from the task's *intent* — P1.B-01 explicitly asks the implementor to determine the convention empirically — but it's called out because the breakdown's own task description assumed a simpler "wrap repeated elements" framing that turned out to be underspecified once tested against the real `extract_records_at_path` contract. This is exactly the kind of finding a spike phase exists to surface before Phase 2 commits production code to a naive version of the rule.
- **[local]** `breakdown.md`'s working-tree copy changed during this session in a way I did not make (see §9 — flagged there, not corrected here per Rule 5: breakdown.md is preserved, never edited by the Implementor).
- **[local]** A real bug was found and fixed in `trial.py` during the deepened comparison: `element_to_normalized`'s text handling originally read only `elem.text` (text before an element's first child), silently dropping text following each child element (`child.tail`) — invisible in the original DNB sample (no mixed content), surfaced only once tested against a genuine mixed-content case (`sample_mixed_content.xml`). Fixed to concatenate `elem.text` + every `child.tail`, then re-verified: (a) still produces the exact same result on the original DNB sample (P1.B-02/03 re-run, unchanged), and (b) now byte-identical to `xmltodict`'s output on the mixed-content sample. This is exactly the kind of gap a spike is supposed to catch before Phase 2 ports the convention as production code — noted, not swept aside.
- No `[contract]` or `[plan]` deviations — this phase produced no production code, so there is no contract to change, and the plan's architecture was not challenged (verdict is GO).

## 6. Contract Changes — for the Reconciler

None. This phase produced no production code, no model/schema/API changes, and no new persisted dependency (only a confirmed *convention* for Phase 2 to implement as real code).

## 7. Tests & Verification

This phase intentionally has no automated test suite (Rule 2; plan.md §7 Phase 1 Artifacts: "throwaway trial code... not production code"). Verification was manual, per the breakdown's own Testing Notes:

**P1.A-02 (raw parse + XXE check)** — actual output:
```
root tag (namespaced): {http://www.loc.gov/zing/srw/}searchRetrieveResponse
...
PASS: defusedxml raised EntitiesForbidden — external entity declaration rejected, not resolved. NFR1 holds for this candidate.
```

**P1.B-01 (normalization)** — actual output (repeatable pairs found):
```
Repeatable (parent, child) pairs found (max count > 1 anywhere): [('dc', 'creator'), ('dc', 'identifier'), ('dc', 'subject'), ('records', 'record')]
```
`dc.creator` confirmed: `["Mustermann, Maxwell [Verfasser]"]` (record[0], 1 occurrence) / absent (record[1]) / `["Kaur, Lakhveer [Herausgeber]", "Kumar, Pushpendra [Herausgeber]"]` (record[2], 2 occurrences) — both single and multi resolve to Python `list`.

**P1.B-02 (`extract_records_at_path`, real function, bare `python`)** — actual output:
```
=== P1.B-02: extract_records_at_path validation (real, unmodified function) ===
data_root_path = 'searchRetrieveResponse.records.record'
Resolved 3 record(s).
First record's dc.title: 'TEST_3 : Untertitel_Test / Maxwell Mustermann' — matches sample.xml. PASS.
Deliberately wrong path 'searchRetrieveResponse.does.not.exist' -> [] (confirms [] means 'wrong path', distinguishing it from a broken normalization, per the function's documented contract). PASS.
```

**P1.B-03 (`SchemaInferenceEngine._walk_record`, real method, via `python manage.py shell -c "..."`)** — actual output:
```
--- record[0] flattened (13 paths) ---
  recordSchema = 'oai_dc'
  ...
  recordData.dc.creator = '__schema_aop__'
  ...
  recordData.dc.identifier = '__schema_aoo__'
  recordData.dc.identifier.@type = 'tel:ISBN'
  recordData.dc.identifier.#text = '978-3-7408-0015-4 broschiert : EUR 1.00 (DE), EUR 1.00 (AT)'
  ...
Union of all flattened keys across 3 records: 14
```
Zero namespace-prefix leakage in any key (spot-checked all 14 union keys — none contain `:` or `{...}`). Zero colliding keys with contradictory meanings.

**Security Self-Check** (Rule 3):
- **Injection/XSS/Log Injection**: N/A — no user input, no logging of response bodies, no SQL/shell/eval involved anywhere in this throwaway code.
- **Authorization/Secrets**: N/A — no auth, no credentials touched; the sample was fetched via a plain, unauthenticated public SRU query (no API key).
- **Sensitive-data exposure**: the sample is a real captured response, but the queried records are DNB's own test/dummy bibliographic entries (query `woe=test`), not real user PII; `spike-findings.md` includes only short excerpts, not full raw bodies, per project convention.
- **Crypto**: N/A — no crypto code touched.
- **SSRF**: N/A — the sample fetch was a one-off `curl` from this environment for spike purposes, not code going through `BaseHTTPClient`; no SSRF-relevant code path exists in this phase's deliverables.
- **XXE (the core NFR1 concern for this feature)**: explicitly checked — `defusedxml.ElementTree` raised `EntitiesForbidden` against an in-memory external-entity payload; confirmed PASS (see §7 above).
- **Dependency legitimacy**: `defusedxml==0.7.1`, confirmed via `pip show` — real PyPI package (`https://github.com/tiran/defusedxml`), authored by Christian Heimes (CPython core developer), already present in the venv as a transitive dependency of `py-serializable`, not newly added to any requirements file in this phase (per the breakdown's explicit instruction not to edit `requirements.txt` here). Registry-level legitimacy confirmed directly (this environment had live network/PyPI metadata access via `pip show`); CVE status is deferred to Phase 2's own dependency-scanning CI once it becomes a real `requirements.txt` entry.

**Deepened comparison — additional verification** (at the human's request, after the above was already complete):

**Security trial (`xmltodict`)** — actual output, 3 payloads (classic entity-based XXE, billion-laughs entity bomb, bare-DOCTYPE-no-entity) at default settings (`disable_entities=True`) and against a hand-written hardened-expat shim:
```
--- (1) classic entity-based XXE, default settings (disable_entities=True) ---
PASS: rejected -> ValueError: entities are disabled
--- (2) billion-laughs entity bomb, default settings ---
PASS: rejected (entity declarations disabled before expansion could occur) -> ValueError: entities are disabled
--- (3) DOCTYPE with ONLY an external subset reference, no entity, default settings ---
ALLOWED at default settings -> {'root': 'hello'} (matches defusedxml.ElementTree's own default posture — neither candidate forbids DTD outright by default)

--- same 3 payloads against the hardened-expat shim (forbid_dtd=True) ---
PASS (classic XXE): hardened shim rejected -> DTDForbidden
PASS (billion laughs): hardened shim rejected -> DTDForbidden
PASS (benign external-subset-only DOCTYPE): hardened shim rejected -> DTDForbidden
```

**Dependency legitimacy (`xmltodict`)**: `xmltodict==1.0.4`, confirmed via `pip show` — real PyPI package (`https://github.com/martinblech/xmltodict`), authored by Martin Blech, 5,700+ GitHub stars, actively maintained (released ~4 months before this spike). Not added to any requirements file in this phase, per the same convention as `defusedxml`.

**Correctness trial (5 samples, both candidates)**: identical normalized output across all 5 (`sample.xml`, `sample_loc_marc.xml`, `sample_mixed_content.xml` — after the `trial.py` fix, `sample_ns_collision.xml`, `sample_large.xml`); both independently re-validated against the real `extract_records_at_path` (LOC MARCXML: 2/2 records resolved by both, 24 `datafield` elements per record matching) and `SchemaInferenceEngine._walk_record` (`walk_record_output.txt` vs `walk_record_output_xmltodict.txt`, identical).

**Performance trial**: 5 timed runs on `sample_large.xml` (5000 records, ~3.1MB):
```
ElementTree: min=264.6ms max=346.3ms avg=305.4ms
xmltodict:   min=509.1ms max=564.4ms avg=527.5ms
ratio (xmltodict/ElementTree): 1.73x
```
Full detail, weighted recommendation, and the research citations behind the maintenance/security-posture claims are in `spike-findings.md` §8.

## 8. Phase Acceptance Criteria

| Criterion (breakdown.md §4) | Status | Evidence |
|---|---|---|
| Normalized structure contains no XML namespace prefixes in any key | **Met** | §7 P1.B-01 output; `walk_record_output.txt`'s 14 union keys spot-checked, none contain `:`/`{...}` |
| Unmodified `extract_records_at_path` returns the expected list of record dicts (not merely non-empty) | **Met** | §7 P1.B-02 output — 3 records resolved, first record's title verified against `sample.xml`'s actual text |
| Unmodified `SchemaInferenceEngine._walk_record` produces a flat map with zero colliding keys | **Met** | §7 P1.B-03 output — 14 distinct keys across 3 records, no contradictory collisions |
| `spike-findings.md` exists with go/no-go verdict + 4 confirmed-convention items | **Met** | `spike-findings.md` §1-4 (library, namespace rule, coercion rule, attribute/text rule) + §7 verdict |

## 9. Needs Your Eyes

- **`breakdown.md`'s working tree copy changed during this session, and I did not make the change.** `git status` at Step 0 (session start) showed it as a clean staged addition (`A`, no working-tree modification). By the time I ran final verification, `git diff` showed it as `AM` with these differences: `[P]` added to P1.A-01's title; P1.B-03's `Dependencies` changed from `P1.B-01 [P — independent of P1.B-02...]` to `P1.B-02` (no longer marked parallel); its `Inputs/Preconditions` text shortened accordingly; and its final two paragraphs (the Handoff Note's last section) appear **duplicated** verbatim. I did not edit this file (per Rule 5, I never do). The content changes happen to match exactly how I actually executed P1.B-02/P1.B-03 (sequentially, not in parallel) — so nothing here contradicts what was built — but the duplicated paragraph looks like an in-progress or interrupted manual edit that you may want to clean up before committing. Please check whether this was an intentional edit (e.g., you adjusting the breakdown live) or something else.
- **The `(parent_tag, child_tag)`-scoped repeatability heuristic is a document-local decision, not a schema-aware one.** It's proven correct for this sample (§3 of `spike-findings.md`), but a hypothetical page where a normally-repeating element occurs exactly once on *every* record on that specific page (no sibling occurrence anywhere in that document to serve as evidence) would have nothing to trigger list-coercion from, and could emit a scalar instead of a list for that one page. This wasn't observable with a single fixed sample. Recommend Phase 2 either accept this as the plan's already-acknowledged residual risk (plan.md §12) or consider a per-endpoint schema hint as a later refinement — your call, not a blocker for the GO verdict.
- **Mixed content is now resolved** (was previously unexercised) — see §5's deviation note: a real bug was found and fixed. Worth your attention not because it's still open, but because it demonstrates the value of the practical trial you asked for — the original spike's design looked correct on paper and would have shipped an unverified gap to Phase 2 without this pass.
- **The library recommendation changed from `defusedxml.ElementTree` to `xmltodict`** between the initial spike and this deepened comparison (§4, §8 of `spike-findings.md`). This is a genuine reversal, not a refinement — please read `spike-findings.md` §8.5's weighted reasoning directly rather than taking my summary on faith, since this is exactly the kind of call `decisions.md`'s `DEC-8` promotion should reflect deliberately, not by default inertia from the first pass.
- **Performance was measured only at a deliberately large, synthetic stress size** (5000 records/~3.1MB) — real SRU API pages are typically far smaller. The ~1.7x gap favoring `ElementTree` is real but its practical significance at actual page sizes is *not yet confirmed*. If Phase 2 wants this fully closed before committing, benchmark against the real target API's typical page size — this is a residual risk, not a blocker for the `xmltodict` recommendation, consistent with plan.md §12's existing pattern of accepting some risks for later confirmation.
- **Nothing here is `[EXTERNAL]`-blocked.** All samples (real and synthetic) were obtained/constructed live during this session; no placeholder or deferred external dependency remains.
- Per the breakdown's Handoff Note, promoting the confirmed conventions to `DEC-8` in `decisions.md` is explicitly a human/Breakdown-Engineer-owned step (Origin: Breakdown Engineer · Phase 1 · REVISE) — I appended my own tactical decisions under separate "Implementor tactical decisions" and "Deepened library comparison" headings instead, and left `DEC-8` itself for you to add after reviewing `spike-findings.md`, including its now-revised library recommendation.

## 10. Suggested Commit Plan

Recent history (`git log --oneline -10`) shows this repo uses plain, imperative one-line subjects (`feat: ...`, no strict Conventional Commits scoping, no body/trailers in recent commits) — matching that convention rather than imposing full Conventional Commits ceremony neither the Requirement/Plan/Breakdown-stage commits used. Note the docs from Stages 1-3 (project-detail.md, requirement.md, plan.md, decisions.md's original content, breakdown.md, the two `_meta/` files) are **already staged** from before this session and are NOT part of this suggested plan — only Phase 1's own new/modified content is:

```
1. feat(docs): add Phase 1 XML normalization spike (spike code + sample)

   Throwaway trial code only — no production files touched. Validates the
   plan's core bet (normalizing XML into dict/list works unmodified with
   the existing pipeline) against a real captured SRU response before
   Phase 2 commits production code to the convention.

   Files: docs/features/001-xml-response-support/phases/phase-1/spike/
   (sample.xml, trial.py, raw_output.txt, walk_record_output.txt)

   Assisted-by: Implementor:claude-sonnet-5 [manage.py shell]

2. docs: record Phase 1 spike findings and go/no-go verdict

   Two coercion-algorithm attempts were tried and failed before the
   confirmed (parent_tag, child_tag)-scoped convention was found — this
   file records why, so Phase 2 doesn't have to re-derive it. Verdict: GO.

   Files: docs/features/001-xml-response-support/phases/phase-1/spike-findings.md

3. docs: append Phase 1 tactical decisions and close out the phase record

   Records the library/algorithm/convention choices made during
   implementation (distinct from the DEC-8 promotion reserved for a human/
   Breakdown Engineer step per breakdown.md's Handoff Note), and updates
   active-context.md's phase-tracking pointer.

   Files: docs/features/001-xml-response-support/decisions.md (append),
   docs/_meta/active-context.md,
   docs/features/001-xml-response-support/phases/phase-1/implementation.md

4. feat(docs): trial xmltodict as a second Phase 1 candidate, fix a mixed-
   content bug found in the process

   The original spike recommended defusedxml.ElementTree without trialing
   xmltodict. Trialing both surfaced that the breakdown's assumed
   defusedexpat companion package is dead (Python 3.3-only), that modern
   xmltodict already blocks entities by default, and a real bug in the
   ElementTree implementation that only a genuine mixed-content test case
   could have caught.

   Files: docs/features/001-xml-response-support/phases/phase-1/spike/
   trial_xmltodict.py, samples/ (4 new sample XMLs),
   raw_output_xmltodict.txt, walk_record_output_xmltodict.txt;
   trial.py (mixed-content fix, re-verified against the original sample)

   Assisted-by: Implementor:claude-sonnet-5 [manage.py shell, WebSearch, WebFetch]

5. docs: revise Phase 1 library recommendation to xmltodict, record the
   deepened comparison

   Reliability (active maintenance) and Maintainability (less custom code,
   caught the mixed-content bug where the alternative didn't) outweigh
   Security, which is now a tie at default settings on this project's
   Python version — a materially different picture than the original DEC-2
   framing assumed. Performance favors ElementTree (~1.7x at stress-test
   size) but is flagged, not treated as settled, pending a real-page-size
   benchmark.

   Files: docs/features/001-xml-response-support/phases/phase-1/
   spike-findings.md (§1, §6, new §8), decisions.md (append),
   implementation.md
```

Review `implementation.md` §9 first (the `breakdown.md` drift, the revised library recommendation, and the performance-benchmarking flag), then `spike-findings.md` §8 for the full comparison, then the `spike/` code if you want to verify either trial yourself.
