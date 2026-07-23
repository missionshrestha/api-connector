# Phase 1 Spike Findings — XML Normalization Feasibility

Feature: `001-xml-response-support` · Phase 1 · Generated against commit `44a191c`
Artifacts: `phase-1/spike/sample.xml`, `phase-1/spike/trial.py`, `phase-1/spike/trial_xmltodict.py`, `phase-1/spike/raw_output.txt`, `phase-1/spike/raw_output_xmltodict.txt`, `phase-1/spike/walk_record_output.txt`, `phase-1/spike/walk_record_output_xmltodict.txt`, `phase-1/spike/samples/` (4 additional samples)

**Revision note**: §1 originally recommended `defusedxml.ElementTree` without trialing `xmltodict`. At the human's request, both candidates were subsequently trialed in full — in-depth research plus a practical trial against 5 samples (the original DNB sample, a 2nd real MARCXML source, a synthetic mixed-content case, a synthetic namespace-collision case, and a ~3.1MB/5000-record performance case). §1 and §6 are updated below; the full comparison and revised recommendation are in **§8**.

---

## 1. Library chosen

**Both `defusedxml.ElementTree` and `xmltodict` were trialed** (see §8 for the full comparison). Both produced **byte-identical normalized output** across all 5 samples once one real bug (found via the practical trial, see §8.3) was fixed in the `ElementTree` implementation. **Recommendation: `xmltodict`**, with reasoning in §8.5 — this supersedes the original single-candidate recommendation above. `decisions.md`'s `DEC-8` promotion (per the breakdown's Handoff Note) should reflect this.

## 2. Namespace-stripping rule (confirmed)

Every element and attribute tag is namespace-stripped from its Clark-notation form (`{uri}localname`) down to `localname` via a single regex, before it becomes a dict key — per DEC-5. Example from the sample: `{http://purl.org/dc/elements/1.1/}creator` → `creator`; `{http://www.w3.org/2001/XMLSchema-instance}type` (an attribute) → `type` → `@type` (see §4). No cross-namespace key collision was observed in this sample (see §6).

## 3. Single-vs-list coercion rule (confirmed) — the spike's central finding

**The naive convention — wrap every child element in a list unconditionally, regardless of occurrence count — was tried first and found to BREAK path resolution.** `extract_records_at_path` (`backend/api_connector/services/pagination/utils.py:16-42`) walks a dot-path by repeated `current = current.get(part)`, requiring every *intermediate* segment's value to be a `dict` (a `list` has no `.get()`). Wrapping a genuinely-singular container like `<records>` (appears exactly once in the whole document) in a 1-item list breaks the very next segment's `.get("record")` call, since `list.get` doesn't exist — `extract_records_at_path` returns `[]` silently (indistinguishable from "wrong path" without adding debug output, which is exactly the false-negative failure mode Task P1.B-02 warned about).

**Confirmed convention**: a two-pass algorithm, scoped by `(parent_tag, child_tag)` pair, not a flat per-tag-name count (a flat global count over-generalizes — see the note in `trial.py`'s P1.B-01 section: `title` appears once per record, so 3 times total across 3 records, and a naive flat count would wrongly mark it "repeatable" even though no single `<dc>` element ever has more than one `<title>`).

- **Pass 1** walks the document once and records, for every `(parent_tag, child_tag)` pair, the *maximum* number of times `child_tag` occurs under any single instance of `parent_tag` anywhere in the document.
- **Pass 2** builds the dict/list tree. A child tag is coerced into a list if EITHER it occurs more than once under this specific parent instance, OR the `(parent_tag, child_tag)` pair's max-count (from Pass 1) is greater than 1 — so a parent's lone occurrence of an otherwise-repeatable tag still yields a list.

**Concrete before/after proof**, using `dc:creator` — the sample's designed single-vs-multi case (`(dc, creator)` max-count = 2, from record[2]):

| Record | Raw occurrence count | Normalized value |
|---|---|---|
| `record[0]` (`recordPosition=1`) | 1 (`"Mustermann, Maxwell [Verfasser]"`) | `["Mustermann, Maxwell [Verfasser]"]` — **list of 1** |
| `record[1]` (`recordPosition=2`) | 0 (absent) | key absent entirely (matches JSON's "optional field" convention) |
| `record[2]` (`recordPosition=3`) | 2 | `["Kaur, Lakhveer [Herausgeber]", "Kumar, Pushpendra [Herausgeber]"]` — **list of 2** |

Both the single-occurrence and multi-occurrence cases resolve to a Python `list` at the identical dot-path (`...dc.creator`), consistently — the FR4 requirement holds under this convention. The same pattern was independently confirmed with `dc:subject` (2/1/1 occurrences → all three resolve to lists) and `dc:identifier` (3/3/6 → all lists). Meanwhile genuinely-singular fields (`title`, `publisher`, `date`, `recordData`, `dc` itself) stay plain scalars/dicts, which is what keeps `extract_records_at_path`'s traversal working.

## 4. Attribute/text-content key convention (confirmed)

`@attr` / `#text` convention (requirement.md §10's suggested default), applied as follows:
- Every attribute becomes a `@name` key (namespace-stripped), sibling to the element's other content.
- Non-empty text content becomes a `#text` key **only when the element also has attributes or children** (genuine mixed content) — e.g. `dc:identifier` in the sample carries a meaningful `xsi:type` attribute (`tel:ISBN`, `dnb:IDN`, `tel:URN`, `tel:URL`) alongside its text value, normalizing to `{"@type": "tel:ISBN", "#text": "978-3-7408-0015-4 ..."}`.
- A pure-text leaf element with **no** attributes or children (e.g. `dc:title`, `dc:publisher`) collapses directly to its text value (a plain string), matching how a JSON API would represent a simple string field — avoiding an unnecessary `{"#text": "..."}` wrapper on the common case.

This preserves attribute data (12 `xsi:type` attributes in the sample, all surfaced under `@type` keys — none silently dropped) while keeping the common case (plain string leaves) as clean as an equivalent JSON body.

## 5. P1.B-02 and P1.B-03 results

**P1.B-02 — `extract_records_at_path` (real, unmodified function)**: **PASS**. Called with `data_root_path = "searchRetrieveResponse.records.record"` against the normalized structure — resolved exactly 3 records; the first record's `recordData.dc.title` matched the sample's actual title text verbatim. A deliberately wrong path (`"searchRetrieveResponse.does.not.exist"`) returned `[]`, confirming the distinction between "wrong path" and "broken normalization" that the task required checking for.

**P1.B-03 — `SchemaInferenceEngine._walk_record` (real, unmodified method, run via `python manage.py shell`)**: **PASS**. Flattened all 3 records to dot-path maps (11–13 paths each). Confirmed:
- Zero namespace-prefix leakage in any key (every key is a clean, human-readable dot-path — e.g. `recordData.dc.identifier.@type`, `recordData.dc.creator`).
- Zero key collisions with contradictory meanings across the 3 records (union of 14 distinct keys; keys present in only some records, e.g. `recordData.dc.type` only in `record[2]`, are simply absent elsewhere — not colliding).
- The repeated-element sentinel behavior described in `_walk_record`'s own docstring held exactly as documented: primitive-only lists (`creator`, `subject`) emitted `ARRAY_OF_PRIMITIVES_SENTINEL`; a list-of-dicts (`identifier`, since each item is `{"@type": ..., "#text": ...}`) emitted `ARRAY_OF_OBJECTS_SENTINEL` plus recursed child paths for the first item only (`identifier.@type`, `identifier.#text`) — matching the codebase's existing JSON-array handling with zero code changes.

## 6. Residual risks not fully resolved

- **Namespace-collision edge case (plan.md §12)**: not observed in this sample — no two distinct source elements shared the same local name after stripping different namespaces. This remains a real, accepted risk (per DEC-5) for feeds unlike this one; not exercised here since the sample didn't happen to contain it.
- **Mixed content**: not observed in the *original* DNB sample, but exercised via a synthetic sample in the deepened comparison (§8.3) — **resolved**, with one caveat: the first `ElementTree`-based implementation had a real bug (silently dropped all text after the first child element) that only surfaced once a genuine mixed-content case was tested; fixed, see §8.3. `xmltodict` handled it correctly with no custom code from the start. Treat this as a lesson, not just a footnote: an untested code path is unverified regardless of how principled its design looks on paper.
- **The `(parent_tag, child_tag)`-scoped repeatability heuristic is document-local, not cross-page.** It correctly handles single-vs-multi occurrence *within one document* (proven in §3), but a genuinely-repeating element that happens to have exactly 1 occurrence on some OTHER page, where it *never* co-occurs with a sibling occurrence anywhere in that specific page's document, would still resolve as a list correctly ONLY IF that document's own structure gives the heuristic evidence to work with (i.e., some other record on the SAME page shows 2+ occurrences under the same parent tag, as `record[2]`'s creators did here). A page where a normally-repeating element occurs exactly once **on every record on that page** (no record on that page shows 2+) would have no local evidence to trigger the list coercion, and could produce a scalar instead of a `list` for that field on that one page — a real limit of a schema-agnostic, per-document heuristic. Not observable with a single fixed sample; noted for Phase 2 to consider (e.g., accepting this as an edge case matching plan.md §12's acknowledged residual risk, or reconsidering per-endpoint schema hints in a later phase).

## 7. Go/No-Go Verdict

**GO.** All three gate conditions (plan.md §6) hold against this real, captured SRU sample:
1. Normalizing real-world XML (namespaced, SRU/`oai_dc`/Dublin-Core-shaped) into the dict/list convention succeeded, with **no namespace prefixes in any key**.
2. The unmodified `extract_records_at_path` resolved the correct record list via a `data_root_path`-style dot-notation string, given the confirmed normalization convention.
3. The unmodified `SchemaInferenceEngine._walk_record` produced a flat, non-colliding, human-readable path→value map from a normalized record, matching its existing JSON-array sentinel behavior exactly.

The single-chokepoint, zero-downstream-changes design (DEC-1) holds. Phase 2 should implement the confirmed convention as production code:
- namespace-stripping via Clark-notation regex (§2)
- the two-pass, `(parent_tag, child_tag)`-scoped list-coercion algorithm (§3) — **this is the one piece of real algorithmic complexity Phase 2 needs to port faithfully**; a naive flat-count or unconditional-list approach will NOT work, per §3's finding
- the `@attr`/`#text` convention, with the pure-text-leaf collapse optimization (§4)

**Recommendation for `decisions.md`**: promote this convention to a new `DEC-8` entry (per the breakdown's Handoff Note) before Phase 2's breakdown is generated, citing this file — including the library recommendation revised in §8.

---

## 8. Deepened Library Comparison — `defusedxml.ElementTree` vs `xmltodict`

Both candidates from `decisions.md` DEC-2 were trialed in full: in-depth research on maintenance/security posture, then a practical trial applying the **identical** normalization convention (§2-4 above) against 5 samples — the original DNB sample, a 2nd real MARCXML source (Library of Congress SRU), and 3 synthetic samples built specifically to exercise cases neither real sample happened to contain (mixed content, a namespace collision, and a ~3.1MB/5000-record performance case).

### 8.1 Research findings

**`defusedxml`** (the `ElementTree` candidate's library): version `0.7.1`, last released 2021; a `0.8.0rc2` has sat unreleased on PyPI since September 2023. A September 2023 Python core-development discussion ([discuss.python.org](https://discuss.python.org/t/status-of-defusedxml-and-recommendation-in-docs/34762)) confirms the package is effectively dormant but **still the recommended choice** for untrusted XML, because — even though modern Python's stdlib XML stack has picked up real protections on its own (see below) — `defusedxml` is the only one that documents and guarantees that posture rather than relying on it as an implementation detail. Authored by Christian Heimes, a CPython core developer; small, stable, auditable surface (this feature only needs `.fromstring()`/`.parse()`).

**`xmltodict`**: version `1.0.4` (installed here), released ~4 months before this spike — actively maintained, 5,700+ GitHub stars, healthy issue/PR activity. Critically, **modern `xmltodict` has a built-in `disable_entities=True` default** that sets an `EntityDeclHandler` rejecting any entity declaration outright — a real, independent safety mechanism the original DEC-2 assumption ("xmltodict alone is not XXE-safe") did not account for, because that assumption predates this hardening being added upstream.

**The specific companion package the breakdown named for option (b), `defusedexpat`, is dead** — last released 2013, only supports Python 3.3/3.4, and cannot install cleanly against this project's Python 3.11+/3.12 stack. This matters: if the team wants a hardened `xmltodict` parser beyond its own default, the originally-planned path doesn't exist anymore. A ~20-line replacement shim is straightforward (§8.2) and was built and tested here, reusing `defusedxml.common`'s own exception classes and the exact handler-hardening technique `defusedxml.ElementTree.DefusedXMLParser` already applies internally — but this is new code the project would own, not an off-the-shelf dependency.

**Modern Python's actual XXE posture** (Python 3.11+/3.12, this project's stack), confirmed via the same discussion thread plus direct source inspection of the installed `defusedxml`/`xmltodict` packages:
- The vendored `libexpat` since Python 3.8 has built-in "billion laughs" / quadratic-blowup protection (byte-count amplification thresholds), independent of any third-party library.
- SAX/DOM/`ElementTree`-family parsers have not resolved *external* entities by default since Python 3.7.1 (no `ExternalEntityRefHandler` is set unless something explicitly sets one).
- Neither candidate forbids a **bare `DOCTYPE` with no entity declaration and no external subset actually fetched** at its own default settings — this is true of *both* `defusedxml.ElementTree`'s own defaults (`forbid_dtd=False`) and `xmltodict`'s (`disable_entities` only blocks entity *declarations*, not the DOCTYPE line itself) — so this is not a gap unique to either candidate, contrary to what DEC-2's original framing implied.

### 8.2 Practical security trial (empirical, not just research)

All payloads tested as **in-memory strings only**, never persisted, per the original P1.A-02 task's security-check convention.

| Payload | `defusedxml.ElementTree` (defaults) | `xmltodict` (defaults, `disable_entities=True`) |
|---|---|---|
| Classic XXE (`<!ENTITY xxe SYSTEM "file:///etc/passwd">`) | **Rejected** — `EntitiesForbidden` | **Rejected** — `ValueError: entities are disabled` |
| Billion-laughs entity bomb (nested `<!ENTITY>` expansion) | **Rejected** — `EntitiesForbidden` (blocked at entity-declaration time, before any expansion) | **Rejected** — `ValueError: entities are disabled` (same: blocked at declaration time) |
| Bare `<!DOCTYPE root SYSTEM "http://.../x.dtd">`, no entity declared | **Allowed** (matches `defusedxml.ElementTree`'s own `forbid_dtd=False` default; the external subset is not actually fetched, since no `ExternalEntityRefHandler` is set) | **Allowed** (same reasoning; `disable_entities` has nothing to fire on since no entity is declared) |

Both candidates are **equally safe by default** against the two attacks that actually matter (entity-based file disclosure, billion-laughs) on this project's Python version — a materially different picture than DEC-2's original framing ("xmltodict alone is not XXE-safe; do not trial it without a defused parser"), which reflected an older, pre-hardening version of `xmltodict`.

For teams wanting to also forbid the bare-DOCTYPE case (stricter than either candidate's default), a hand-written shim (`trial_xmltodict.py`'s `_HardenedExpatModule`, ~20 lines, reusing `defusedxml.common`'s exception classes) was built and verified to reject all 3 payloads including the bare-DOCTYPE case, by replicating `defusedxml.ElementTree.DefusedXMLParser`'s own handler-setting technique directly on a raw `xml.parsers.expat` parser. This is a legitimate option for either candidate — `defusedxml.ElementTree.parse(..., forbid_dtd=True)` already supports the equivalent for the `ElementTree` path with zero extra code; `xmltodict` would need this shim (or equivalent) since `defusedexpat` is dead.

### 8.3 Practical correctness trial — 5 samples

| Sample | Real/synthetic | What it tests | Result |
|---|---|---|---|
| `sample.xml` (DNB, original) | Real | Namespaces, single-vs-multi coercion, attributes | **Identical** normalized output, both candidates |
| `samples/sample_loc_marc.xml` (LOC MARCXML) | Real, 2nd source | Different namespace style (`zs:`-prefixed, not default), `tag`/`ind1`/`ind2`/`code`-attribute-driven repeated elements (24 `datafield` elements per record) | **Identical** normalized output, both candidates; both resolved 2/2 records via the real `extract_records_at_path` |
| `samples/sample_mixed_content.xml` | Synthetic | An element with interleaved text and child elements (`<description>text <em>x</em> more text <code>y</code> even more text</description>`) | **Found a real bug**: the first `ElementTree` implementation only read `elem.text` (text *before* the first child), silently dropping every child's `.tail` text (text *after* each child) — collapsed "This book covers ... and more, aimed at ... readers." down to just "This book covers". `xmltodict` handled it correctly with no extra code. **Fixed** in `trial.py` (concatenate `elem.text` + every `child.tail`, matching `xmltodict`'s own `cdata_separator=""` + `strip_whitespace=True` semantics exactly) — re-verified byte-identical to `xmltodict`'s output afterward. |
| `samples/sample_ns_collision.xml` | Synthetic | Two different namespaced elements (`dc:title`, `mods:title`) as siblings, same local name after stripping | **Identical** for both candidates: both silently merge into `"title": ["The Great Gatsby", "Le Grand Gatsby (French edition subtitle)"]` — a concrete demonstration of the accepted DEC-5 collision risk, not a difference between candidates. |
| `samples/sample_large.xml` (synthetic, ~3.1MB/5000 records) | Synthetic | Performance at a stress-test size well above real per-page SRU response sizes | See §8.4 |

Once the mixed-content bug was fixed, **every one of the 5 samples produced byte-identical normalized output between the two candidates**, and both were re-verified against the real, unmodified `extract_records_at_path` and `SchemaInferenceEngine._walk_record` with matching results (`walk_record_output.txt` vs `walk_record_output_xmltodict.txt` — identical).

### 8.4 Performance

5 timed runs on `sample_large.xml` (5000 synthetic records, ~3.1MB — a deliberately large stress case; real SRU API pages are typically tens of records, not thousands, per `PaginationConfig`'s existing page-size defaults):

| | min | max | avg |
|---|---|---|---|
| `defusedxml.ElementTree` | 264.6 ms | 346.3 ms | 305.4 ms |
| `xmltodict` | 509.1 ms | 564.4 ms | 527.5 ms |

`xmltodict` is consistently **~1.7x slower** than `ElementTree` on this workload — attributable to `xmltodict`'s Python-level SAX event handling plus this trial's own two-pass convention needing a full extra `force_list=True` parse for the occurrence-counting pass. At real target page sizes (tens of records, likely low hundreds of KB at most), the absolute difference is expected to be a few milliseconds — not a residual risk expected to matter in practice, but flagged for Phase 2 to benchmark against the actual target API's real page sizes before treating this as settled (plan.md §12's existing residual-risk pattern).

### 8.5 Weighted recommendation

Weighed against the Decision Priority Order (Business value → Correctness → Security → Reliability → Scalability → Maintainability → Cost → Speed of implementation):

- **Business value / Correctness**: tied — both produce identical, verified output across all 5 samples once the `ElementTree` bug was fixed.
- **Security**: effectively tied at default settings for the attacks that matter today (§8.2) — contrary to the original DEC-2 framing, this is no longer a clear differentiator on this project's Python version.
- **Reliability**: favors `xmltodict` — actively maintained (`1.0.4`, ~4 months old) vs. `defusedxml`'s dormant status (last real release 2021, an unreleased `0.8.0rc2` since 2023). For a dependency the codebase will carry indefinitely, active upstream maintenance matters for long-term patchability.
- **Scalability**: favors `ElementTree` — ~1.7x faster at the stress-test size (§8.4). Likely immaterial at real page sizes, but a genuine, measured difference.
- **Maintainability**: favors `xmltodict` — needs *less* custom code to reach the same convention (native `@`/`#text`, automatic pure-text-leaf collapse, and a `force_list` callable that maps directly onto the same two-pass algorithm), and it handled mixed content correctly from the start where the hand-rolled `ElementTree` walk had a real, demonstrated bug. Less custom code is less surface for exactly this kind of subtle miss.
- **Cost / Speed of implementation**: favors `xmltodict` slightly, for the same less-custom-code reason.

**Recommendation: `xmltodict`.** Security is not the deciding factor here (both are comparably safe today); the tie-breakers are `xmltodict`'s active maintenance and its smaller custom-code surface, which already caught one real bug during this trial that the `ElementTree` path would have shipped with with un-noticed if it had not been tested against mixed content specifically. The performance gap is real but is not expected to matter at actual SRU page sizes — Phase 2 should confirm this against the real target API before treating it as fully closed. This recommendation is not unanimous by every axis — `ElementTree` is the better choice if raw performance on very large pages is a project priority — but on balance, and per this codebase's own stated priority order, `xmltodict` is the stronger overall choice.

Either choice remains reversible per DEC-2's own reversibility note; both implementations (`trial.py`, `trial_xmltodict.py`) are preserved in `spike/` for Phase 2 to port from directly.
