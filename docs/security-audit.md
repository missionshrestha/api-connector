# API Connector — Security Audit

**Audit completed:** Phase 8 — Hardening & Polish  
**Status:** CLEARED for production deployment with documented caveats

---

## 1. Credential Pipeline Audit

| Code Path | File | Expected Behavior | Audit Result |
|---|---|---|---|
| Create profile | `serializers/connection_profile.py → ConnectionProfileCreateSerializer.create()` | `encrypt_dict(credentials)` before `AuthConfig.objects.create()`; wrapped in `transaction.atomic()` | ✅ PASS |
| Update profile | `serializers/connection_profile.py → ConnectionProfileUpdateSerializer.update()` | Decrypt existing, merge new (falsy values skipped), `encrypt_dict(merged)` before `auth_config.save()` | ✅ PASS |
| Read profile list | `serializers/connection_profile.py → ConnectionProfileReadSerializer.Meta.fields` | `encrypted_credentials` absent from fields list; only `credentials_summary` (plaintext JSONB) returned | ✅ PASS — verified `"encrypted_credentials" not in Meta.fields` |
| Connection test | `services/connection_test/service.py → _step_auth_injection()` | `decrypt_to_dict()` in-memory; result never logged; credentials dict garbage-collected after request | ✅ PASS |
| Schema inference | `views/endpoint.py → schema_infer()` | `decrypt_to_dict()` at action start; credentials passed to engine; never serialized in response | ✅ PASS |
| Data preview | `views/endpoint.py → preview()` | Same pattern as schema_infer | ✅ PASS |
| Detect data root | `views/endpoint.py → detect_data_root_action()` | Same pattern | ✅ PASS |
| OAuth CC token fetch | `services/oauth_cc_token.py → get_token(), _fetch_token()` | Access token encrypted via `encryption_service.encrypt()` before `OAuthToken` write; raw token never logged | ✅ PASS |
| OAuth AC token storage | `services/oauth_ac_token.py → store_tokens()` | Both access and refresh tokens encrypted before write; `update_refresh_if_none` parameter prevents silent loss of refresh token | ✅ PASS |
| OAuth callback | `views/oauth_callback.py → oauth_callback()` | Authorization code received; token exchange via HTTPS; access+refresh tokens immediately encrypted; code never logged | ✅ PASS |

**`__str__` security check:**
- `AuthConfig.__str__`: returns `"AuthConfig for profile {id}"` — no credential fields exposed ✅
- `OAuthToken.__str__`: returns `"OAuthToken({token_type}) for profile {id}"` — no token fields exposed ✅

---

## 2. Logging Audit

### `BaseHTTPClient` (Phase 1)
Log format: `"HTTP %s %s → %s (%dms)", method, url_no_qs, status_code, latency_ms`

- URL query string stripped: `url_no_qs = url.split("?")[0]` ✅  
  **Rationale:** `APIKeyAuthHandler` with `delivery="query"` injects API key as URL parameter. Logging full URL would expose API keys in server logs.
- Response body NOT logged ✅
- Request headers NOT logged ✅
- Credentials dict NOT logged ✅

### `OAuthCCTokenService._fetch_token()` (Phase 3)
Log format: `"OAuth CC token fetch for profile: HTTP %s (%dms)", response.status_code, latency_ms`
- Token endpoint body NOT logged ✅
- Access token NOT logged ✅

### `OAuthACTokenService._refresh_access_token()` (Phase 4)
Same pattern — only status code and latency ✅

### `oauth_callback` view (Phase 4)
Log format: `"OAuth AC token exchange: profile=%s HTTP %s (%dms)", connection_profile_id, status_code, latency_ms`
- Authorization code NOT logged ✅
- Token response body NOT logged ✅

### `PaginationEngine._request_with_retry()` (Phase 5)
Retry warning: `"PaginationEngine HTTP %s on attempt %d/%d for %s — retrying in %.1fs", status_code, ..., url_no_qs, delay`
- Uses `url_no_qs` (query string stripped) ✅

### `DataPreviewService.preview()` (Phase 7)
Log format: `"DataPreview: endpoint=%s row_limit=%d rows_returned=%d has_more=%s columns=%d duration_ms=%d"`
- `rows` values NOT logged ✅
- `raw_response_body` NOT logged ✅

**Overall: PASS — No credential values, response bodies, or API keys appear in any log line.**

---

## 3. SSL/TLS Audit

### `BaseHTTPClient` Default
- Function signature: `ssl_verify: bool = True` — correct default ✅
- Passed to: `httpx.Client(verify=ssl_verify, timeout=timeout)` ✅

### Connection Test Network Connectivity Step
- Uses `profile.ssl_verify` (not hardcoded) ✅

### OAuth Token Endpoints
- `OAuthCCTokenService._fetch_token()`: `httpx.Client(timeout=30)` — defaults `verify=True` ✅
- `OAuthACTokenService._refresh_access_token()`: same ✅
- Intentional: OAuth token endpoints are always HTTPS and must always verify certificates

### `PaginationEngine._request_with_retry()`
- `httpx.Client(verify=ssl_verify, timeout=timeout)` — passes profile's `ssl_verify` ✅

### Production Requirement
`SECURE_SSL_REDIRECT` defaults to `False` (acceptable for dev). **Production deployments MUST set `SECURE_SSL_REDIRECT=True`** in the environment. A Django system check warning is registered in `ApiConnectorConfig.ready()` when `not DEBUG and not SECURE_SSL_REDIRECT`.

**See:** `docs/operations.md` Section 1 for environment variable reference.

---

## 4. SSRF Evaluation

**Decision (ADR-011):** Optional RFC 1918 / loopback / link-local IP blocking via `SSRF_PROTECTION_ENABLED` setting (default `False`).

**Blocked ranges when enabled:**
- `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` — RFC 1918 private
- `127.0.0.0/8` — IPv4 loopback  
- `169.254.0.0/16` — Link-local (AWS instance metadata at 169.254.169.254)
- `::1/128` — IPv6 loopback
- `fc00::/7` — IPv6 ULA

**Call sites protected:** `BaseHTTPClient.request()`, `OAuthCCTokenService._fetch_token()`, `OAuthACTokenService._refresh_access_token()`, `oauth_callback` token exchange.

**Known limitation (DNS TOCTOU):** Hostname is resolved at validation time and again at connection time. A DNS rebinding attack could return a public IP at validation, then a private IP at connection. This is an accepted MVP-scope limitation.

**Production requirement:** Deployments in shared cloud environments or multi-tenant contexts **MUST** set `SSRF_PROTECTION_ENABLED=True`.

---

## 5. Authentication Boundary

All ViewSets use `permission_classes = [AllowAny]`. This is **intentional and documented** (`[ASSUMPTION]` tags in view code since Phase 2).

**Architecture assumption:** This module is intended to be embedded in a host platform that provides its own authentication layer. Requests reaching the `api_connector` endpoints must have already passed through the host platform's auth middleware.

**Production integration requirement:** Ensure all paths to `/api/connector/...` are protected by the host platform's authentication before reaching Django. Never expose the `api_connector` API directly to the public internet without a host-level auth layer.

---

## 6. Encryption Key Management

- `ENCRYPTION_KEY` loaded exclusively from `settings.ENCRYPTION_KEY` (via `django-environ`) ✅
- Sourced from environment variable only — never committed to VCS ✅
- `backend/.env` excluded from git via `.gitignore` ✅
- `backend/.env.example` committed (no real values) ✅
- Validated at first use by `EncryptionService._get_fernet()` — raises `ImproperlyConfigured` on empty or invalid key ✅

**Key rotation procedure:** See `docs/operations.md` — Section 2.

---

## 7. CI Enforcement

The following security check runs on every push and pull request via `.github/workflows/backend-ci.yml`:
Security — No direct Fernet imports outside encryption.py (ADR-005)


This step prevents future contributors from bypassing `EncryptionService` by importing `Fernet` directly.

---

## 8. Known Residual Risks

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| SSRF — all outbound HTTP uses user-configured URLs | Medium | `SSRF_PROTECTION_ENABLED` utility available | Set to `True` in shared environments |
| DNS TOCTOU in SSRF validation | Low | Accepted MVP limitation; documented | Enable SSRF + trusted deployment |
| `step_results` stores 2KB body sample (PII possible) | Low | Never logged; host platform owns data retention policy | Host platform must implement retention |
| `sample_value` in `SchemaField` stores one API value per field (PII possible) | Low | Never logged; same as above | Host platform must implement retention |
| `AllowAny` on all ViewSets | High risk if misconfigured | Documented as host-platform assumption | Host platform MUST enforce auth |
| `SSRF_PROTECTION_ENABLED=False` (default) | Medium | Documented; opt-in | Enable in shared deployments |

---

## Audit Sign-off

- All 10 credential code paths: **PASS**
- Logging audit: **PASS** (0 credential values in any log line)
- SSL/TLS defaults: **PASS**
- SSRF: **EVALUATED** — optional protection available
- Auth boundary: **INTENTIONAL** — host-platform assumption documented
- Encryption key management: **PASS**
- CI enforcement: **ACTIVE** (Fernet import check in backend-ci.yml)
- `OAuthACReauthorizationRequired` → HTTP 401: **FIXED** (Phase 8)
- `PaginationEngineError` in preview → HTTP 400: **FIXED** (Phase 8)

