# Active Context

Live pointer: what feature and phase is in flight right now, and what to run next. Every pipeline stage reads this on start and updates specific fields as it works — see each stage's own system prompt for exactly which fields it owns; the short version is in the runbook's marker/field appendix.

**No stage creates this file.** It's set up once, by hand (this is that setup), the first time you use the pipeline on a project. After that, it updates itself as you work — you generally shouldn't need to hand-edit it, only read it.

This pipeline is designed around **one feature in flight at a time**. If you ever run two features in parallel on purpose, every stage will flag the conflict rather than block it — duplicate the "Current Feature" block below per feature if you need to track more than one at once.

---

## Last Full Context Compiler Sweep

*(not yet run)*

<!-- Format once run: 2026-06-30 @ commit a3f9c21 on branch main -->

---

## Current Feature

001-xml-response-support (branch: 001-xml-response-support)

## Phase Status

| Phase | Status | Updated |
| --- | --- | --- |
| 1 | Reconciled — 🟡 YELLOW, see DEV-1/2/3 | 2026-07-23 |
| 2 | Ready for review — 7/7 tasks done, 466 tests passing | 2026-07-23 |
| 3 | Not started | — |
| 4 | Not started | — |

## Next Action

Human: review the uncommitted delta (`git diff 069b461e53a61b73e227c8c43ce78f9347a2d21e`) per `phases/phase-2/implementation.md`'s suggested commit plan, then commit. Look first at `services/pagination/engine.py` (the `[REVIEW-GATE]` P2.B change — already reviewed once at the halt, human confirmed proceed, but it's still the highest-blast-radius diff in the phase) and `services/xml_parser.py` (the list-coercion port fidelity). All 7 tasks complete: P2.A (XML parsing module), P2.C (`Endpoint.response_format` field/migration/serializers/defaulting), P2.B (format branch). Full backend suite: 466 passed, zero regression on the existing JSON pipeline. After commit: Reconciler — Phase 2.

---

*This file changes constantly — every phase, often every session. That's expected; it's the entire point. If it ever looks stale against what you know actually happened, trust the actual git state and the phase's own `implementation.md`/`reconciliation.md` over this file, and update it by hand to match.*
