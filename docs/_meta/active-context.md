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
| 4 | Not started | — |

## Next Action

Human: 9 files are already staged (`engine.py`, `data_preview.py`, the 3 phase-3 test files, `decisions.md`, an earlier `active-context.md`, `phase-3/breakdown.md`, `phase-3/implementation.md`) — a bare `git commit` would commit only those. First run `git add docs/_meta/active-context.md docs/project-detail.md docs/features/001-xml-response-support/phases/phase-3/reconciliation.md` to pick up this Reconciler's memory-bank updates and its report, then review with `git diff --cached` and commit. After that: Breakdown Engineer — Phase 4. See `phase-3/reconciliation.md` (475 tests passing, independently re-run and confirmed, 0 regressions; DEV-1: pre-existing, format-agnostic `_next_url` query-string-drop bug, carried forward for Phase 4 to consider before its e2e validation runs).

---

*This file changes constantly — every phase, often every session. That's expected; it's the entire point. If it ever looks stale against what you know actually happened, trust the actual git state and the phase's own `implementation.md`/`reconciliation.md` over this file, and update it by hand to match.*
