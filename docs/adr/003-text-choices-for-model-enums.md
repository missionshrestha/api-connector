# ADR-003: TextChoices over IntegerChoices for Model Enums

## Status
Accepted

## Context
Django model fields that represent a fixed set of values can use either
`IntegerChoices` (stores 0, 1, 2… in the DB) or `TextChoices` (stores
human-readable strings like "bearer", "oauth_cc").

## Options Considered
**Option 1 — TextChoices:** stores "oauth_cc" in the DB column. Human-readable
in raw psql output. Immune to reordering. Validated at write time by max_length.

**Option 2 — IntegerChoices:** stores 0, 1, 2… Slightly more compact on disk.
Ordering-sensitive: inserting a new value between existing ones changes every
integer's meaning. Column contents are opaque without the enum definition.

## Decision
TextChoices.

## Rationale
1. The integer-ordering fragility is a production data-corruption risk with no
   upside at the data volumes this application targets.
2. A TextChoices max_length that is too short raises `DataError` at write time —
   a loud, immediate failure. IntegerChoices has no equivalent guard.
3. Direct database inspection (psql, pg_dump, analytics queries) is self-documenting.

## Consequences
- All CharField choices fields use `max_length` set to a value safely larger than
  the longest enum value string (e.g., max_length=30 for InferredType whose longest
  value "array_of_primitives" is 19 chars).
- If enum values must change after migration 0001_initial.py is applied, a data
  migration is required to update stored string values. This is safer and more
  explicit than renumbering integers.
