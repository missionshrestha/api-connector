# ADR-010: PaginationEngine as Python Generator

## Status
Accepted

## Context
Phase 6 needs to fetch up to 300 records for schema inference.
Phase 7 needs to fetch records up to a row_limit for data preview.
Both need early-exit capability.

## Options Considered
Option 1 — Generator (yield): caller controls iteration via for/next.
  Early-exit without fetching remaining pages.
Option 2 — List return: all pages fetched before any processing begins.
  Phase 6 must wait for all pages even if 3 pages of 100 records are enough.

## Decision
Generator (yield).

## Rationale
Phase 6 needs early-exit after 3 pages regardless of total count.
Memory is bounded by page_size, not total_records.
Row-limited Phase 7 previews don't fetch unnecessary pages.

## Consequences
IRREVERSIBLE: all callers use generator protocol (for records in engine.paginate(...)).
paginate() cannot be changed to list-return without breaking Phases 6 and 7.
