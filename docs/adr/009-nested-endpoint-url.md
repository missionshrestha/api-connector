# ADR-009: Nested Endpoint URL Structure

## Status
Accepted

## Context
Endpoints belong to a ConnectionProfile. URL structure could be flat
(/api/connector/endpoints/?profile=<id>) or nested
(/api/connector/profiles/<pk>/endpoints/).

## Decision
Nested URL: /api/connector/profiles/<profile_pk>/endpoints/

## Rationale
Access control hierarchy is self-evident in the URL.
get_queryset() filtering by profile_pk prevents cross-profile access.
Aligns with REST resource nesting semantics.

## Consequences
All endpoint consumers must supply profile_pk in the URL path.
Changing to flat URL would require consumer updates.
