# ADR-006: Synchronous httpx (httpx.Client) for MVP

## Status
Accepted

## Context
BaseHTTPClient uses httpx for outbound API calls. httpx supports both synchronous
(httpx.Client) and asynchronous (httpx.AsyncClient) operation. Django views can
be sync or async; Phase 0 uses WSGI.

## Options Considered
**Option 1 — Synchronous (httpx.Client + sync Django views):**
WSGI-native. Blocking per request. Simple. No event loop management.
PaginationEngine in Phase 5 can be a plain generator (no async generators).

**Option 2 — Asynchronous (httpx.AsyncClient + async Django views):**
Non-blocking under concurrent load. Requires ASGI (Daphne, Uvicorn).
Async generators add significant complexity to the Phase 5 PaginationEngine.
All Django views touching HTTP must be async.

## Decision
Synchronous (Option 1).

## Rationale
Expected usage: single-user interactive sessions, not concurrent batch operations.
WSGI is Phase 0's established baseline. Migrating to async requires changing
BaseHTTPClient, all call sites, all Django views, and the test suite. The
complexity cost exceeds the concurrency benefit at MVP scale. Phase 8 can
revisit if profiling shows worker thread saturation.

## Consequences
This decision is IRREVERSIBLE without significant refactoring.
- All views that call BaseHTTPClient are synchronous.
- socket.getaddrinfo() in Phase 3 is safe without run_in_executor().
- Migration to async: change BaseHTTPClient, all call sites, all Django
  views using HTTP, and the entire test suite.
