══════════════════════════════════════════════════════════════
Phase 1 Reconciliation · Technical Spike: XML Normalization Feasibility
Baseline: 44a191cfc289a9b10308960bf3c545f6b52fe0f7 on branch 001-xml-response-support   ·   Verdict: 🟡 YELLOW
══════════════════════════════════════════════════════════════

1. PHASE REALITY REPORT

   Artifact Status (one entry per planned artifact, breakdown.md §3):

     spike/sample.xml (P1.A-01)
       Status:  FOUND
       Details: Real, unmodified DNB SRU response. Confirmed by inspection: 6 distinct
                namespace declarations (`srw` default, `dc`, `dnb`, `tel`, `xsi`, `oai_dc`),
                a proven single/absent/multi split on `dc:creator` (1 / 0 / 2 occurrences
                across the 3 records), and 12 meaningful `xsi:type` attributes. Matches
                plan.md §6's "prefer a real captured response" preference.

     spike/trial.py — raw parse + XXE check (P1.A-02)
       Status:  FOUND
       Details: Re-ran myself under bare `python`. Output matches implementation.md
                verbatim: native output is an unwalked `Element` tree in Clark notation;
                `EntitiesForbidden` raised against an in-memory classic-XXE payload. PASS.

     spike/trial.py — normalization convention (P1.B-01)
       Status:  FOUND
       Details: Re-ran myself. Namespace-stripped, two-pass `(parent_tag, child_tag)`-scoped
                list coercion, `@attr`/`#text` convention with pure-text-leaf collapse — all
                confirmed working exactly as `spike-findings.md` §2-4 describe, including the
                `dc.creator` 1/absent/2 → list/absent/list proof.

     spike/trial.py — extract_records_at_path validation (P1.B-02)
       Status:  FOUND
       Details: Called the real, unmodified `extract_records_at_path`
                (`backend/api_connector/services/pagination/utils.py:16`) myself. Resolved
                3 records; first record's `dc.title` matched `sample.xml` verbatim. A
                deliberately wrong path returned `[]`, confirming the "wrong path" vs.
                "broken normalization" distinction the task required. PASS, independently
                reproduced.

     spike/trial.py — SchemaInferenceEngine._walk_record validation (P1.B-03)
       Status:  FOUND
       Details: Ran via `python manage.py shell -c "..."` myself (not bare python — this
                function reads `settings.SCHEMA_INFERENCE_MAX_DEPTH`). Output matches
                implementation.md exactly: 13/11/13 flattened paths per record, 14 union
                keys, zero namespace-prefix leakage (verified programmatically — no key
                contains `:` or `{`), zero contradictory collisions, correct
                ARRAY_OF_PRIMITIVES/ARRAY_OF_OBJECTS sentinel behavior. PASS.

     spike-findings.md (P1.B-04)
       Status:  FOUND
       Details: All 7 required items present (library choice + rationale, namespace rule,
                coercion rule with before/after proof, attribute/text convention, P1.B-02/03
                results, residual risks cross-referenced to plan.md §12, GO verdict per
                plan.md §6's gate). Each cites a concrete observation from this phase's own
                trial, not a restated requirement.

     ADDED (not in original breakdown, added at the human's explicit request per
     implementation.md §1 — extending, not replacing, the required deliverables above):
       - spike/trial_xmltodict.py, spike/samples/ (4 files: sample_loc_marc.xml,
         sample_mixed_content.xml, sample_ns_collision.xml, sample_large.xml),
         spike/raw_output_xmltodict.txt, spike/walk_record_output_xmltodict.txt
       - decisions.md's "Deepened library comparison" section
       - spike-findings.md §8

   Tests: No automated test suite exists for this phase, by design (breakdown.md §4
   "Expected automated coverage: None" — this is throwaway spike code, not production
   code, per plan.md §7 Phase 1 Artifacts). Verification was manual re-execution, done
   independently by me, not by trusting implementation.md's pasted output:

   ```
   $ python trial.py                         (bare python, from backend/, venv active)
   PASS: defusedxml raised EntitiesForbidden — external entity declaration rejected.
   Repeatable (parent, child) pairs found: [('dc','creator'),('dc','identifier'),
                                             ('dc','subject'),('records','record')]
   Resolved 3 record(s). First record's dc.title: 'TEST_3 : ...' — matches sample.xml. PASS.
   Deliberately wrong path -> [] . PASS.

   $ python manage.py shell -c "... trial.run_walk_record_check()"
   record[0]: 13 paths, record[1]: 11 paths, record[2]: 13 paths.
   Union of all flattened keys across 3 records: 14
   (spot-checked programmatically: 0/14 keys contain ':' or '{' — zero namespace leakage)

   $ python trial_xmltodict.py
   3/3 security payloads handled identically to defusedxml's own posture (classic XXE
   and billion-laughs rejected by default; bare-DOCTYPE-no-entity allowed by both,
   documented as a shared non-differentiating gap); hardened-expat shim rejects all 3.

   Programmatic byte-identical check (sort_keys JSON comparison, all 5 samples,
   run by me, not from implementation.md's claim):
     sample.xml            IDENTICAL (ElementTree vs xmltodict)
     sample_loc_marc.xml    IDENTICAL
     sample_mixed_content.xml IDENTICAL
     sample_ns_collision.xml IDENTICAL
     sample_large.xml       IDENTICAL

     LOC MARCXML: both candidates resolved 2/2 records via the real
     extract_records_at_path, agreeing with each other on datafield counts per record
     (24 and 28 — see Convention & Dependency Check note below on a minor inaccuracy
     in implementation.md's paraphrase of this figure).

     walk_record_output.txt vs walk_record_output_xmltodict.txt: diff -> IDENTICAL.

   Performance (single re-run, not the full 5-run average implementation.md reports):
     ElementTree: 257.59 ms   xmltodict: 477.75 ms   (ratio 1.85x — consistent with
     the claimed ~1.7x average; single-run variance, not a discrepancy).
   ```

   No `[EXTERNAL]`-tagged placeholders exist in this phase (breakdown.md confirms none;
   implementation.md §9 confirms none) — nothing to cross-check on that front.

   Convention & Dependency Check:
     No conventions in project-detail.md apply to this phase's own artifacts (spike code
     under docs/, not backend/api_connector/ — no ruff/pytest convention violated; the
     spike scripts are explicitly exempt per plan.md §7). No amendments in
     constitution.md (file exists, all sections state "none — default applies").

     New dependencies: `defusedxml==0.7.1` (already present transitively via
     `py-serializable`, not newly added) and `xmltodict==1.0.4` (newly pip-installed
     ad hoc into the venv for this trial, per P1.A-02's explicit instruction not to edit
     requirements.txt this phase — confirmed: `git diff <baseline> -- backend/` is empty,
     no requirements file touched). Both confirmed real, canonically-named PyPI packages
     via `pip show` (defusedxml: Christian Heimes/CPython core dev; xmltodict: Martin
     Blech, 5,700+ stars). CVE status: this environment has live PyPI/registry access —
     ran `pip-audit` myself against both pinned versions directly (not deferred):
     **"No known vulnerabilities found."** for both.

     Minor inaccuracy (non-significant): implementation.md §7 states the LOC MARCXML
     sample's 2 records each contain "24 datafield elements" — I confirmed the real
     counts are 24 and 28 respectively (not 24/24). Both candidates agree with each
     other on this (24 and 28, matching), so the substantive claim — both candidates
     resolve the same 2 records with identical structure — still holds; this is a
     reporting imprecision in implementation.md's paraphrase, not a normalization defect.
     Not escalated to a DEV-N: it affects no downstream contract, memory-bank entry, or
     Phase 2 decision.

   Unplanned Changes:
     - `.gitignore`'s working-tree modification (adds `context/*`, `.claude/*`) predates
       this phase — project-detail.md §12 (generated same day, against the same baseline
       commit) already documents this exact uncommitted diff as pre-existing. Not a
       Phase 1 Implementor change.
     - **`breakdown.md`'s own working-tree copy changed during the Implementor's session,
       and the Implementor states they did not make the change** (implementation.md §9).
       I confirmed the anomaly by reading the file: P1.A-01's title carries `[P]`;
       P1.B-03's `Dependencies` reads `P1.B-02` (not parallel-marked); and the Handoff
       Note's final two paragraphs were duplicated verbatim (lines 374-383). This is not
       something I can attribute — it's not in git history (the file was never
       committed, so there's no prior version to diff against) and I have no way to
       independently confirm who/what edited it. It did not affect this phase's actual
       verification (the content changes coincidentally matched how P1.B-02/P1.B-03 were
       actually executed, sequentially). **Update, post-review**: at the human's explicit
       instruction, I removed the duplicated paragraph directly (the `[P]` tag and
       `Dependencies` drift were left as-is — they're accurate to what actually happened
       and not a defect). This is the one edit in this reconciliation that departs from
       Rule 2's normal "you don't edit breakdown.md" — done only because the human
       explicitly asked me to fix it myself, not on my own initiative.
     - No drive-by edits to unnamed files, no silent library/pattern swap outside what
       decisions.md documents, no unflagged security-sensitive code, no
       `[REVIEW-GATE]`/`[IRREVERSIBLE]` task in this phase (breakdown.md confirms neither
       exists here) to check for a silently-skipped gate.

   Significant Deviations:

     DEV-1: List-coercion algorithm needed a scoped two-pass design, not the
            simpler framing breakdown.md's task description assumed
       Planned:   P1.B-01's task description frames the work as "coerce single and
                  multiple occurrences of a repeated element into a list" without
                  specifying an algorithm shape.
       Actual:    A flat, unconditional "wrap every child" rule breaks
                  `extract_records_at_path`'s dict-only intermediate-segment traversal;
                  a flat per-tag-name count over-generalizes (wrongly flags `title` as
                  repeatable). The confirmed, working convention is a two-pass algorithm
                  scoped by `(parent_tag, child_tag)` pair — confirmed by reading
                  trial.py's `_collect_max_occurrence_counts`/`element_to_normalized`
                  and independently re-running it.
       Reasoning: This is the one piece of real algorithmic complexity Phase 2 must
                  port faithfully (spike-findings.md §3, §7). A Phase 2 breakdown written
                  against a naive framing would generate code that breaks
                  `extract_records_at_path` on any singular non-repeating container.
       Action:    No project-detail.md update (no production code/convention exists yet
                  to correct). Carried forward to Phase 2 — see §3.

     DEV-2: Library recommendation reversed from the tentative defusedxml.ElementTree
            call to xmltodict; the breakdown/DEC-2's named companion package for the
            xmltodict candidate (`defusedexpat`) is confirmed dead
       Planned:   decisions.md DEC-2 (context, pre-Phase-1) frames candidate (b) as
                  "`xmltodict` layered over a defused parser (`xmltodict.parse(...,
                  expat=defusedexpat...)`" — i.e., assumes `defusedexpat` is the viable
                  hardening path, and DEC-2's initial framing treats `xmltodict` alone
                  as not XXE-safe.
       Actual:    `defusedexpat` last released 2013, Python 3.3/3.4-only, cannot install
                  against this project's Python 3.11+/3.12 — confirmed by the
                  Implementor's research (spike-findings.md §8.1) and consistent with
                  what I could independently confirm via `pip show`/PyPI metadata access.
                  Modern `xmltodict` (1.0.4) has its own built-in `disable_entities=True`
                  default that independently blocks entity-based attacks — I re-ran the
                  3-payload security trial myself and confirmed: classic XXE and
                  billion-laughs rejected by both candidates at default settings; a bare
                  DOCTYPE with no entity is allowed by both (a shared, not
                  differentiating, gap). With Security now a tie, Reliability
                  (`xmltodict` actively maintained vs. `defusedxml`'s dormant 0.7.1) and
                  Maintainability (less custom code, and it avoided DEV-3's bug from the
                  start) are the deciding factors — I independently re-verified all 5
                  samples produce byte-identical normalized output between the two
                  candidates.
       Reasoning: Phase 2's breakdown will design the production XML parsing module
                  around whichever library is chosen. If it's generated assuming the
                  original tentative `defusedxml.ElementTree` lean or references the dead
                  `defusedexpat` package, it will need immediate correction. This is
                  exactly the kind of finding a spike phase exists to surface before
                  Phase 2 commits production code to a wrong assumption.
       Action:    No project-detail.md update (no dependency has been added to
                  requirements.txt yet — correctly, per this phase's scope). Carried
                  forward to Phase 2, and — per breakdown.md's Handoff Note — this is
                  exactly what the human/Breakdown-Engineer's `DEC-8` promotion step
                  must reflect. See §3.

     DEV-3: A real bug was found and fixed in trial.py's mixed-content text handling
       Planned:   P1.B-01's Testing Notes: "observe the candidate's behavior and record
                  it... as a known limitation if the sample happens to contain any... do
                  not block go/no-go" — i.e., the breakdown treated mixed content as an
                  optional, non-blocking observation, not an expected bug.
       Actual:    The original `element_to_normalized` implementation read only
                  `elem.text` (text before an element's first child), silently dropping
                  every child's `.tail` text (text after each child) — confirmed by
                  reading trial.py's inline comment at the text-handling block and by
                  independently re-running the fixed version against
                  `sample_mixed_content.xml`, confirming output is now byte-identical to
                  `xmltodict`'s (which handled this correctly natively, with no custom
                  code). The bug was invisible in the original DNB sample (no mixed
                  content) and only surfaced via the synthetic sample built for the
                  deepened comparison.
       Reasoning: If Phase 2 ports the `ElementTree`-based approach (rather than
                  adopting `xmltodict`, per DEV-2's recommendation), it must concatenate
                  `elem.text` + every child's `.tail`, not just read `elem.text` — an
                  easy-to-miss gap that would silently truncate any real API response
                  containing mixed content (e.g. rich-text/HTML-ish description fields).
       Action:    No project-detail.md update (throwaway spike code, not production).
                  Carried forward to Phase 2 as a required implementation detail if the
                  `ElementTree` path is chosen over `xmltodict`. See §3.

2. MEMORY BANK UPDATES (project-detail.md)

   None required. This phase produced no production code, no new persisted dependency
   (both trialed libraries were installed ad hoc into the venv only, per the breakdown's
   explicit instruction not to touch requirements.txt/requirements-dev.txt this phase —
   confirmed: `git diff <baseline> -- backend/` is empty), and no change to any existing
   project convention, tech-stack entry, or footgun documented in project-detail.md.
   Everything this phase confirmed belongs in `decisions.md`/`spike-findings.md` (feature-
   scoped) rather than `project-detail.md` (project-wide, verified-codebase-state scoped)
   — correctly, per this phase's own design (plan.md §7: "not production code").

3. CARRY-FORWARD TO NEXT PHASE (Phase 2 — XML Parsing Core & Format Routing)

   Stage 3 (Breakdown Engineer) must account for the following when generating Phase 2's
   breakdown, all independently verified by me in this reconciliation (not taken on the
   Implementor's word):

   - **Confirmed normalization convention** (spike-findings.md §2-4, independently
     re-verified): namespace-stripping via a single Clark-notation regex; the two-pass,
     `(parent_tag, child_tag)`-scoped list-coercion algorithm (DEV-1) — Phase 2 must port
     this exact algorithm, not a naive flat-count or unconditional-list approach, either
     of which is proven broken; the `@attr`/`#text` convention with pure-text-leaf
     collapse.
   - **Revised library recommendation: `xmltodict`, not `defusedxml.ElementTree`**
     (DEV-2) — reversed from the pre-Phase-1 tentative lean, on Reliability +
     Maintainability grounds, Security now a tie. `defusedexpat` (the breakdown/DEC-2's
     named companion package for the `xmltodict` path) is dead and must not be
     referenced as a dependency; if `forbid_dtd`-level hardening beyond `xmltodict`'s own
     `disable_entities=True` default is wanted, the ~20-line hardened-expat shim in
     `trial_xmltodict.py`'s `_HardenedExpatModule` is the viable path, reusing
     `defusedxml.common`'s exception classes.
   - **If Phase 2 instead chooses the `ElementTree` path**, it must concatenate
     `elem.text` + every child's `.tail` for text content (DEV-3) — not just `elem.text`
     — to avoid silently truncating mixed-content fields. `xmltodict` handles this
     correctly with no custom code.
   - **`DEC-8` has now been promoted** (at the human's explicit instruction, appended by
     me to `decisions.md` after this reconciliation's independent re-verification) —
     this is normally a Breakdown-Engineer/human step per breakdown.md's Handoff Note,
     done here only because directly asked for, not on my own initiative (Rule 2). It
     carries the confirmed convention and the revised `xmltodict` recommendation
     forward with the `Origin: Breakdown Engineer · Phase 1 · REVISE` tag the Handoff
     Note specifies, and cites this reconciliation as the verification behind it.
     Stage 3 can now cite `DEC-8` directly rather than re-deriving from
     `spike-findings.md`.
   - **Residual risks to carry into Phase 2's own risk tracking** (all already
     documented in spike-findings.md §6/§8.4, re-confirmed by me, not newly discovered):
     cross-namespace same-local-name collision (DEC-5's accepted risk, concretely
     demonstrated via `sample_ns_collision.xml`); the `(parent_tag, child_tag)` heuristic
     is document-local, not schema-aware — a field repeating exactly once on every
     record of some future page, with no other same-page evidence of repetition, could
     resolve as a scalar instead of a list; `xmltodict`'s ~1.7x performance overhead vs.
     `ElementTree`, measured only at a synthetic 5000-record/~3.1MB stress size — not yet
     confirmed at real SRU page sizes (tens of records), flagged for Phase 2 to
     benchmark before treating as settled.
   - **`breakdown.md`'s duplicated Handoff Note paragraph has been removed** (§1
     Unplanned Changes) — fixed directly at the human's request. The `[P]` tag and
     `P1.B-03` dependency drift were left in place, since both are accurate to how the
     phase actually executed and not a defect.

4. ESCALATION

   N/A — verdict is YELLOW, not RED. No escalation to FIX or Architect REVISE.

5. WHAT I COULD NOT VERIFY (honesty)

   - **Who or what changed `breakdown.md`'s working tree during the Implementor's
     session.** implementation.md §9 states the Implementor did not make the edit; I
     have no git history to diff against (the file was never committed) and no session
     logs outside this conversation to inspect. I can only confirm the anomaly is real
     and still present (duplicated Handoff Note paragraph, `[P]` tag and dependency
     drift on P1.A-01/P1.B-03) — the human is better positioned to know whether this was
     their own live edit mid-session or something else.
   - **Whether the ~1.7x ElementTree/xmltodict performance gap matters at real SRU page
     sizes.** I re-confirmed the stress-test measurement itself (single re-run: 1.85x,
     consistent with the claimed 5-run average of ~1.73x) but did not benchmark against
     an actual target API's typical page size — that requires live traffic against a
     real endpoint, which is Phase 2/4's job, not reproducible from this spike alone.
   - **Whether any XML-returning API beyond the 2 real samples (DNB, LOC) would surface
     a normalization gap neither sample happened to contain.** Both real samples are
     Dublin-Core/MARCXML-flavored SRU responses from library-science sources; plan.md
     §12 already names this as an accepted residual risk, not something this
     reconciliation can close.
   - **Deep security review of the hand-written `_HardenedExpatModule` shim.** I
     confirmed it behaves as claimed against the 3 tested payloads (functional
     verification), but did not audit it for correctness beyond those specific inputs —
     it's optional spike-only code, not something Phase 2 is required to adopt, and a
     full security review of a hand-rolled expat-hardening shim is outside a
     reconciliation's scope if Phase 2 does decide to carry it into production.
   - **Same-model blind spot**: this reconciliation and the Phase 1 Implementor both ran
     on the same model family. I mitigated this by independently re-executing every
     claim from first principles (re-running both trial scripts myself, re-deriving the
     byte-identical comparison programmatically, running my own `pip-audit`) rather than
     accepting implementation.md's pasted output at face value — but a shared blind spot
     in judgment (e.g., both agreeing a convention is "sane" when a human reviewer with
     different domain experience might not) cannot be ruled out by this method. Nothing
     here is a substitute for the human's own read of spike-findings.md §8.5's weighted
     library reasoning, which the Implementor itself flagged as worth reading directly
     (implementation.md §9).
