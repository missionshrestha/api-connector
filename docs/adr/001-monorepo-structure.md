# ADR-001: Monorepo Structure

## Status
Accepted

## Context
Backend and frontend could live in separate repositories or in one monorepo.

## Options Considered
**Option 1 — Monorepo:** `backend/` and `frontend/` under one root; shared CI context;
TypeScript types live in `frontend/src/shared/types/` without a publish pipeline.

**Option 2 — Separate repos:** independent CI; requires a shared types package with
versioned publish step; cross-repo coordination for phase work.

## Decision
Monorepo.

## Rationale
Shared TypeScript types and cross-cutting CI changes touch one repository context.
Separate repos add a publish pipeline overhead with no benefit at this team size.

## Consequences
Locks in all relative file paths in CI workflows and tooling configuration.
All downstream ADRs assume `backend/` and `frontend/` as sibling directories.
