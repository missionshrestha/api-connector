# ADR-005: Single Call-Site Encryption Pattern

## Status
Accepted

## Context
Any code path that encrypts or decrypts credentials must be auditable. Without
a central enforcement point, encrypt/decrypt calls could spread across models,
serializers, views, and management commands — making a Phase 8 security audit
require a full-codebase search.

## Decision
All encryption and decryption goes through `EncryptionService` in
`api_connector/services/encryption.py`. Direct imports of
`from cryptography.fernet import Fernet` anywhere outside `encryption.py`
are a security violation.

## Rationale
- Security audit scope: one file to verify, not a grep across the codebase.
- Key rotation: touching one file rotates the algorithm for the entire system.
- HSM integration (future): replace `Fernet(key.encode())` with an HSM client
  in one place.

## Consequences
- Module-level singleton `encryption_service` is the single import for all callers.
- The `_fernet` instance is cached after first use; key rotation requires
  a process restart (or setting `_fernet = None` on the singleton).
- `cryptography.fernet.InvalidToken` from corrupt data is NOT caught inside
  EncryptionService — it propagates to callers, who handle credential corruption
  at the appropriate layer.

## Enforcement
Phase 8 CI check:
  grep -r "from cryptography.fernet import" backend/api_connector --include="*.py"
  | grep -v "encryption.py"
  → must return no output.
