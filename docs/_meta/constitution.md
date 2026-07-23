# Pipeline Constitution

Project-specific amendments to the default pipeline-wide conventions baked into Requirement Architect, Breakdown Engineer, Implementor, and Reconciler. Every one of those four stages reads this file at the start of every invocation, if it exists.

**Where a section below is silent or marked "no amendment," each stage falls back to its own built-in default.** This file does not need to repeat anything that's already correct as the default — only what your team wants to override.

This file is **read-only infrastructure**. None of the five pipeline stages ever writes to it. Edit it by hand, whenever the team needs to change a default, and commit it like any other project file.

---

## Decision Priority Order

Default — used by Requirement Architect, Breakdown Engineer, and Implementor whenever they weigh an adapt-vs-replace call or recommend between two valid approaches:

**Business value → Correctness → Security → Reliability → Scalability → Maintainability → Cost → Speed of implementation.**

**Amendment:** *(none — default applies)*

<!--
To override, replace the line above with your team's order and a one-line reason. Example:
**Amendment:** Security → Correctness → Business value → Reliability → Maintainability → Scalability → Cost → Speed — regulated industry; compliance posture takes precedence over time-to-market.
-->

---

## Additional "Adapt Over Disrupt" Worked Examples

The built-in Constitution (in Requirement Architect, Breakdown Engineer, and Implementor) ships three default worked examples: encryption/secrets, connector testing, and frontend UI components. Add domain-specific examples here once your team has repeatedly hit an adapt-vs-replace pattern those three don't cover.

**Amendment:** *(none yet — add examples here as they come up)*

<!--
Example format:
*Worked example (data export formats):* the project already exports to CSV through a single `exporters/csv_exporter.py` module behind a shared `Exporter` interface. A new format (e.g., Parquet) should implement that same interface, not introduce a parallel export pipeline. Replace only if the existing interface genuinely can't express the new format's requirements.
-->

---

## Other Pipeline-Wide Conventions

Anything else worth standardizing across every feature: a non-default branch-naming convention (the default is `branch name = NNN-slug`), a stricter or looser definition of Compact/Standard/Large scope for this team, a compliance mandate that should always force a replace rather than an adapt, a different default for when Reconciler is mandatory vs. optional, etc.

**Amendment:** *(none yet)*

---

*Last updated: — by —. This file should change rarely. If you find yourself editing it every week, that's a signal the amendment belongs in `project-detail.md` (project-specific fact) rather than here (pipeline-wide rule).*
