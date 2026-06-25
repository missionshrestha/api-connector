# API Connector — Operations Runbook

This runbook documents procedures required for production deployment and ongoing maintenance.

---

## 1. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Required | None | Django cryptographic key. Generate: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DATABASE_URL` | Required | None | PostgreSQL connection URL. Format: `postgres://USER:PASSWORD@HOST:PORT/DBNAME`. **SQLite is not supported.** |
| `ENCRYPTION_KEY` | Required | `""` | Fernet symmetric key for credential encryption at rest. See Section 2 for rotation. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `DEBUG` | Dev only | `False` | Django debug mode. **Must be `False` in production.** |
| `ALLOWED_HOSTS` | Required | `localhost,127.0.0.1` | Comma-separated list of allowed Django hostnames |
| `CORS_ALLOWED_ORIGINS` | Required | `http://localhost:5173` | Comma-separated list of allowed frontend origins (no trailing slash) |
| `SECURE_SSL_REDIRECT` | Required in prod | `False` | Redirect HTTP → HTTPS. **Must be `True` in production.** |
| `OAUTH_REDIRECT_URI` | OAuth AC only | `http://localhost:8000/api/connector/oauth/callback/` | Callback URL after OAuth consent. See Section 3. |
| `SSRF_PROTECTION_ENABLED` | Recommended | `False` | Block RFC 1918/loopback IPs in outbound HTTP calls. **Set `True` in shared/cloud environments.** |
| `SCHEMA_INFERENCE_MAX_DEPTH` | Optional | `10` | Maximum recursion depth for the schema walker. Increase only for APIs with deeply nested structures. |
| `VITE_API_BASE_URL` | Frontend required | `http://localhost:8000` | Backend URL for frontend API calls (set at build time). |
| `CI_ENCRYPTION_KEY` | CI required | None | GitHub Actions secret. Generate a fresh Fernet key and store as a repository secret named `CI_ENCRYPTION_KEY`. |

---

## 2. ENCRYPTION_KEY Rotation Procedure

> **⚠️ WARNING: Rotating this key invalidates ALL stored encrypted credentials.**  
> Back up the database before rotating. This operation is irreversible once committed.

### When to Rotate

- When `ENCRYPTION_KEY` is compromised (credential exposure risk)
- As part of periodic cryptographic key hygiene (recommended: annually)
- When migrating to a new secrets management system

### Pre-rotation Checklist

1. [ ] Database backup completed and verified restorable
2. [ ] New Fernet key generated (never reuse an old key):
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
 New key stored securely in secrets manager (Vault, AWS Secrets Manager, GCP Secret Manager)
 Maintenance window scheduled (Django workers must be stopped during rotation)
Rotation Procedure
Step 1: Dry-run verification (verify old key decrypts all records)

cd backend
python manage.py rotate_encryption_key \
  --old-key="$CURRENT_ENCRYPTION_KEY" \
  --new-key="$NEW_ENCRYPTION_KEY" \
  --dry-run
Expected output: ✓ Dry run PASSED — N records verified, 0 errors

Step 2: Stop all Django workers (prevents partial writes during rotation)

Step 3: Execute rotation

python manage.py rotate_encryption_key \
  --old-key="$CURRENT_ENCRYPTION_KEY" \
  --new-key="$NEW_ENCRYPTION_KEY"
Type ROTATE when prompted. The entire operation runs in a single transaction.atomic().

Step 4: Verify rotation succeeded

python manage.py shell -c "
from api_connector.services.encryption import encryption_service
from api_connector.models import AuthConfig
ac = AuthConfig.objects.first()
if ac:
    print(encryption_service.decrypt_to_dict(ac.encrypted_credentials))
    print('Verification: PASS')
else:
    print('No AuthConfig records exist')
"
Step 5: Update ENCRYPTION_KEY in all deployment environments to the new value.

Step 6: Restart all Django worker processes (clears cached Fernet instance).

Rollback Procedure
If rotate_encryption_key fails, the transaction is rolled back automatically. The old key is still valid. Do not update ENCRYPTION_KEY in your environment until rotate_encryption_key exits successfully.

3. OAuth Authorization Code Configuration
Redirect URI Requirements
Each deployment environment requires a different OAUTH_REDIRECT_URI value, and this value must exactly match what is registered in each OAuth provider's application settings.

Environment	OAUTH_REDIRECT_URI
Local development	http://localhost:8000/api/connector/oauth/callback/
Staging	https://staging-api.your-domain.com/api/connector/oauth/callback/
Production	https://api.your-domain.com/api/connector/oauth/callback/
Trailing slash matters. Providers perform exact string matching.

Provider-Specific Setup
Google OAuth 2.0:

Google Cloud Console → Credentials → OAuth 2.0 Client ID → Authorized redirect URIs
Add the exact OAUTH_REDIRECT_URI value for each environment
Use separate Client IDs for staging vs. production (recommended)
GitHub OAuth:

Settings → Developer Settings → OAuth Apps
GitHub allows only one redirect URI per app — create separate apps for each environment
Generic OIDC:

Add OAUTH_REDIRECT_URI to the provider's allowed redirect URI list
Enable code response type and authorization_code grant type
PKCE Note
This implementation uses PKCE (RFC 7636) with S256 challenge method. Most modern OAuth providers support PKCE. If a provider rejects code_challenge_method=S256, the oauth_initiate view at api_connector/views/connection_profile.py must be updated to omit the PKCE parameters — consult the provider's documentation.

4. OAuthACState Cleanup
The api_connector_oauth_ac_state table accumulates one record per OAuth authorization attempt. Records are safe to delete after use or expiry.

Automatic Cleanup (Recommended)
Schedule weekly:

# Add to crontab (crontab -e):
0 3 * * 0 /path/to/venv/bin/python /path/to/manage.py cleanup_oauth_ac_states
Or run manually:

python manage.py cleanup_oauth_ac_states
What the Command Deletes
used=True AND created_at < (now - 24 hours) — completed authorization flows
expires_at < (now - 24 hours) — expired without completion
What the Command Preserves
used=False AND expires_at > now — active authorization flows in progress
Trigger for Manual Cleanup
Monitor the table size: if SELECT COUNT(*) FROM api_connector_oauth_ac_state exceeds 10,000 rows, run cleanup immediately.

5. Branch Protection Setup (Manual Step)
GitHub branch protection must be configured manually after CI workflows run for the first time:

Repository → Settings → Branches → Add branch protection rule
Branch name pattern: main
✅ Require status checks to pass before merging
Required checks: Backend CI / lint-and-test and Frontend CI / lint-and-test
✅ Require branches to be up to date before merging
6. Database Backup Recommendation
Run daily backups via pg_dump:

pg_dump -Fc api_connector_production > backup_$(date +%Y%m%d).dump
Important: The encrypted_credentials and encrypted_token columns are encrypted but backups are still sensitive — an attacker with both the backup file and the ENCRYPTION_KEY can decrypt all credentials. Store backups in a separate, access-controlled location.

Backup + rotation coordination: Take a database backup immediately before rotating ENCRYPTION_KEY. If rotation fails and you need to restore from backup, the restored data will be encrypted with the old key — ensure you still have access to the old key value during the restoration window.

7. Monitoring Checklist
Monitor the following in production:

Metric	Alert Threshold	Action
Django ERROR log entries	Any ERROR	Investigate immediately; API_CONN_099 indicates unexpected exception
POST .../test/ p95 latency	> 5000ms	Check target API health; review ConnectionProfile.request_timeout
POST .../schema/infer/ p95 latency	> 15000ms	Check target API pagination config; reduce max_pages if needed
api_connector_oauth_ac_state row count	> 10,000	Run python manage.py cleanup_oauth_ac_states
Database connection pool saturation	> 80%	Scale Django workers or increase PostgreSQL max_connections
Key Log Entries to Monitor
# Normal operations:
api_connector.connection_test: ConnectionTest completed profile=N overall=True steps=6 duration_ms=N
api_connector.schema_inference: Schema inference: endpoint=N records_sampled=N paths_discovered=N
api_connector.data_preview: DataPreview: endpoint=N row_limit=N rows_returned=N has_more=False

# Warnings requiring attention:
api_connector.schema_inference: WARNING - low sample count (N records) — type inference may be unreliable
api_connector.oauth_cc_token: WARNING - retry N/N for https://...  (rate limiting from OAuth provider)
api_connector.ssrf: WARNING - blocked request to hostname '...' (when SSRF_PROTECTION_ENABLED=True)

# Errors requiring immediate action:
api_connector.exceptions: Unhandled exception in API view: ...  (unexpected 500)
api_connector.oauth_ac_token: ERROR - token data corrupt for profile N  (re-authorization required)
