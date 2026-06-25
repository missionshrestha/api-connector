# API Connector — Operations Runbook

**Scope:** deploying, configuring, and maintaining the API Connector backend in a
shared or production environment.
**Audience:** operators / on-call engineers.
**Related:** [security-audit.md](security-audit.md), [benchmark-results.md](benchmark-results.md),
[ADR-005](adr/005-encryption-single-call-site.md).

---

## 1. Environment configuration

All configuration is environment-driven (`backend/.env`, see `backend/.env.example`).
Settings are read in `config/settings.py`.

| Variable | Required | Production value | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | random 50+ chars | Never reuse across environments. |
| `DEBUG` | Yes | `False` | Defaults to `False`; only `.env` sets it `True`. |
| `ALLOWED_HOSTS` | Yes | your hostname(s) | Comma-separated. |
| `DATABASE_URL` | Yes | Postgres DSN | SQLite is dev-only. |
| `ENCRYPTION_KEY` | Yes | Fernet key (secrets manager) | See §3. Rotating it requires the §3 procedure. |
| `CORS_ALLOWED_ORIGINS` | Yes | frontend origin(s) | Validated against OAuth `redirect_origin`. |
| `SECURE_SSL_REDIRECT` | Yes (prod) | `True` | Forces HTTPS. Defaults `False` for local dev. |
| `SSRF_PROTECTION_ENABLED` | Yes (shared) | `True` | Blocks RFC 1918 / link-local targets. Defaults `False`. |
| `OAUTH_REDIRECT_URI` | If OAuth AC used | public callback URL | Must match the provider registration. |
| `SCHEMA_INFERENCE_MAX_DEPTH` | No | default | Bounds recursive type inference. |

### Generate a Fernet `ENCRYPTION_KEY`

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the value in a secrets manager — **never** commit it. Losing it makes all
stored credentials and OAuth tokens permanently undecryptable.

---

## 2. Pre-deployment checklist

- [ ] `DEBUG=False`
- [ ] `SECURE_SSL_REDIRECT=True`
- [ ] `SSRF_PROTECTION_ENABLED=True` (any shared/cloud environment)
- [ ] `ENCRYPTION_KEY` sourced from a secrets manager, not `.env` on disk
- [ ] `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` restricted to real hosts
- [ ] Database migrations applied: `python manage.py migrate`
- [ ] `python manage.py check --deploy` reviewed
- [ ] Database backup configured (see §6)
- [ ] `cleanup_oauth_ac_states` scheduled (see §4)
- [ ] Branch protection enabled on `main`; both CI workflows green

---

## 3. Encryption key rotation

Per [ADR-005](adr/005-encryption-single-call-site.md), all Fernet operations live
in `services/encryption.py`. The `rotate_encryption_key` command re-encrypts every
`AuthConfig.encrypted_credentials` and `OAuthToken` record from an old key to a new
key inside a **single transaction** — any failure rolls back and the old key stays
valid, so there is no partial-rotation corruption risk.

**Procedure:**

1. **Back up the database first.** This is non-negotiable.
2. Generate a new key (see §1).
3. Dry-run — verifies every record decrypts under the current key, writes nothing:
   ```bash
   python manage.py rotate_encryption_key --old-key=<CURRENT> --new-key=<NEW> --dry-run
   ```
4. If the dry-run reports `0 errors`, execute (you must type `ROTATE` to confirm):
   ```bash
   python manage.py rotate_encryption_key --old-key=<CURRENT> --new-key=<NEW>
   ```
5. Update `ENCRYPTION_KEY` to `<NEW>` in **every** environment.
6. Restart all Django worker processes — the Fernet instance is cached per process.
7. Verify:
   ```bash
   python manage.py shell -c "from api_connector.services.encryption import encryption_service; \
   from api_connector.models import AuthConfig; \
   print(encryption_service.decrypt_to_dict(AuthConfig.objects.first().encrypted_credentials))"
   ```

If the dry-run reports any failures, **do not rotate** — investigate first
(usually a record encrypted under a third, unknown key).

---

## 4. OAuth AC state cleanup

`OAuthACState` rows are single-use CSRF/PKCE artifacts. Used or expired rows are
dead weight and must be purged periodically.

```bash
python manage.py cleanup_oauth_ac_states            # default 24h retention
python manage.py cleanup_oauth_ac_states --retention-hours 1
```

Deletes records that are `used=True` **or** past `expires_at`, older than the
retention window; preserves active (unused + unexpired) authorization flows.
Safe to run at any time and idempotent.

**Schedule weekly via cron:**

```cron
0 3 * * 0 /path/to/venv/bin/python /path/to/manage.py cleanup_oauth_ac_states
```

---

## 5. SSRF protection

The connector makes outbound HTTP on behalf of users (schema inference, preview,
connection test), so it is an SSRF vector. When `SSRF_PROTECTION_ENABLED=True`,
`services/ssrf.py` validates each target URL and rejects RFC 1918 / loopback /
link-local addresses, raising a structured `400` (not a `500`).

- **Always** set `SSRF_PROTECTION_ENABLED=True` in shared/cloud environments.
- It defaults to `False` so local development can hit `localhost` test APIs.

---

## 6. Backups & recovery

- **Database:** automated daily snapshots; verify restore quarterly. Credentials
  and tokens are stored encrypted, so a backup is useless without `ENCRYPTION_KEY`.
- **`ENCRYPTION_KEY`:** stored in a secrets manager with its own backup/version
  history. Losing it = unrecoverable credentials. Treat key + DB as one unit.

---

## 7. Incident response

| Symptom | First checks |
|---|---|
| Preview/inference returns `401` (`API_CONN_041`) | OAuth AC token expired/revoked — user must re-authorize. Expected, not an outage. |
| Many `500`s on outbound calls | Upstream API down, or DNS/network. Check logs for `API_CONN_099`. |
| `ImproperlyConfigured: ENCRYPTION_KEY` at startup | Key missing/malformed in the environment. |
| Decryption failures after deploy | Likely a key mismatch — confirm `ENCRYPTION_KEY` matches the key the data was encrypted with; see §3. |

**Logging:** credentials, tokens, request rows, and raw response bodies are never
logged (OWASP A09). Do not add logging that prints these.

---

## 8. Monitoring

- Watch error rates for `API_CONN_099` (unexpected server errors).
- Track outbound request latency against the NFR targets in
  [benchmark-results.md](benchmark-results.md).
- Alert on growth of `OAuthACState` row count (indicates §4 cleanup not running).
