# ADR-008: Profile API URL Structure

## Status
Accepted

## Context
Profiles could live at /api/profiles/ or /api/connector/profiles/.

## Decision
/api/connector/profiles/

## Rationale
The module is intended to be embedded in a host platform.
Namespace under /connector/ prevents clashes with host application routes.

## Consequences
All Phase 3–7 nested routes follow this prefix:
  /api/connector/profiles/{id}/test/
  /api/connector/profiles/{id}/endpoints/
  /api/connector/profiles/{id}/endpoints/{eid}/schema/
  /api/connector/profiles/{id}/endpoints/{eid}/preview/
