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
| 2 | Reconciled — 🟢 GREEN | 2026-07-23 |
| 3 | Reconciled — 🟡 YELLOW, see DEV-1 | 2026-07-23 |
| 4 | Ready for review (P4.A + P4.B both complete; OD-1 resolved as recommended) | 2026-07-24 |

## Next Action

Human: review `docs/features/001-xml-response-support/phases/phase-4/implementation.md` (full record, §11 has the resolved halt, twice — DNB first, then expanded on request) — both P4.A (UI Surfacing) and P4.B (End-to-End Validation) are done. P4.B was executed via direct backend API calls, not a browser walkthrough (no browser-automation tooling available), against **6 real, live, independent XML APIs** (`docs/e2e-testing-guide-xml.md`, one section each, mirroring `e2e-testing-guide.md`'s structure). It surfaced 3 genuine, pre-existing, format-agnostic app characteristics — a base-URL/path gotcha for single-fixed-endpoint APIs, a dot-notation validator that can't express root-level XML-attribute pagination metadata, and a silent zero-field result when `data_root_path` resolves to scalar records — none fixed this phase, all documented with exact reproduction steps in the new guide's §8 and `implementation.md` §9. All work is an uncommitted delta against baseline `78d2d79`. This is the final phase of `001-xml-response-support` — once reviewed/committed and reconciled, re-run `requirement.md` §5's SC1-SC8 one more time against the fully completed feature (implementation.md §8 AC6 has a first pass already).

---

*This file changes constantly — every phase, often every session. That's expected; it's the entire point. If it ever looks stale against what you know actually happened, trust the actual git state and the phase's own `implementation.md`/`reconciliation.md` over this file, and update it by hand to match.*
