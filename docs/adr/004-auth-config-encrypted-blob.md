# ADR-004: AuthConfig Encrypted Credentials Storage Format

## Status
Accepted

## Context
Per-type credential fields vary in structure:
- API Key: key_name, key_value, delivery, prefix
- Bearer: token, header_name
- Basic: username, password
- OAuth CC: client_id, client_secret, token_endpoint, scopes
- OAuth AC: client_id, client_secret, auth_endpoint, token_endpoint, redirect_uri

A storage format must accommodate all current and future auth types without
schema changes.

## Options Considered
**Option 1 — JSONB blob:** serialize credential dict → JSON string → Fernet
encrypt → store as {"blob": "<ciphertext>"}. Single column in DB.

**Option 2 — Per-field encryption:** one column per credential field
(api_key_value, bearer_token, ...). Requires 10+ nullable columns or
separate per-auth-type tables.

**Option 3 — Separate per-auth-type tables:** AuthConfigAPIKey,
AuthConfigBearer, etc. Maximum type safety at the DB level.

## Decision
JSONB blob (Option 1).

## Rationale
Business value and maintainability. New auth types (Phase 3, 4) add zero new
DB columns. All credential validation is at the application layer (serializers),
where it is easier to test and iterate. Security equivalence: Fernet AES-256-CBC
with HMAC-SHA256 protects the entire blob whether it holds one field or twenty.

## Consequences
- DB cannot query individual credential fields.
- Application layer must decrypt to inspect (EncryptionService.decrypt_to_dict()).
- Acceptable for the access patterns in this system (credential data is accessed
  only at request execution time, never in list/filter queries).
- Column type: PostgreSQL JSONB (mapped from Django JSONField on PostgreSQL).
