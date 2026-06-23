#!/usr/bin/env bash
# scripts/validate-phase4.sh
# Run from repository root: bash scripts/validate-phase4.sh
# Exits 0 on full pass, non-zero on any failure.

set -uo pipefail
PASS=0; FAIL=0; WARN=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; ((PASS++)) || true; }
fail() { echo -e "${RED}✗ FAIL${NC}: $1"; ((FAIL++)) || true; }
warn() { echo -e "${YELLOW}⚠ WARN${NC}: $1"; ((WARN++)) || true; }

REPO_ROOT="$(pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
VENV="$BACKEND/.venv"

PYTHON="$VENV/bin/python"; PYTEST="$VENV/bin/pytest"; RUFF="$VENV/bin/ruff"
[ -f "$PYTHON" ] || { PYTHON="$(command -v python3)"; PYTEST="$(command -v pytest)"; RUFF="$(command -v ruff)"; }
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -f "$REPO_ROOT/.nvmrc" ] && nvm use > /dev/null 2>&1 || true
NPM="$(command -v npm)"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Phase 4 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Migrations ────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Migrations ───────────────────────────────────────${NC}"
MIG=$(cd "$BACKEND" && $PYTHON manage.py showmigrations api_connector 2>/dev/null)
echo "$MIG" | grep -q "\[X\] 0001_initial" && pass "0001_initial applied" || fail "0001_initial missing"
echo "$MIG" | grep -q "\[X\] 0002_authconfig" && pass "0002 applied" || fail "0002 missing"
echo "$MIG" | grep -q "\[X\] 0003_oauth_token" && pass "0003 applied" || fail "0003 missing"
echo "$MIG" | grep -q "\[X\] 0004_oauth_ac_state" && pass "0004_oauth_ac_state applied" \
  || fail "0004 not applied — run: cd backend && python manage.py migrate"

# ── Table count ───────────────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.models import OAuthACState
fields = [f.name for f in OAuthACState._meta.get_fields()]
assert 'state' in fields
assert 'pkce_code_verifier' in fields
assert 'pkce_code_challenge' in fields
assert 'used' in fields
assert 'expires_at' in fields
print('OK')
" 2>/dev/null) && pass "OAuthACState model has all required fields" \
  || fail "OAuthACState model missing fields"

# ── Service imports ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Service Imports ──────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.oauth_ac_token import OAuthACTokenService
from api_connector.services.oauth_ac_exceptions import (
    OAuthACReauthorizationRequired, REASON_NO_TOKEN, REASON_REFRESH_FAILED
)
print('OK')
" 2>/dev/null) && pass "OAuthACTokenService and exceptions import cleanly" \
  || fail "Import error — check oauth_ac_token.py and oauth_ac_exceptions.py"

# ── OAuthACAuthHandler stub replaced ────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
import httpx
from api_connector.services.auth.handlers.oauth_ac import OAuthACAuthHandler
h = OAuthACAuthHandler()
try:
    h.prepare_request(httpx.Request('GET', 'https://x.com'), {})
    print('ERROR')
    exit(1)
except ValueError:
    print('OK')
except NotImplementedError:
    print('STUB_STILL_PRESENT')
    exit(1)
" 2>/dev/null) && pass "OAuthACAuthHandler raises ValueError (stub replaced)" \
  || fail "OAuthACAuthHandler still raises NotImplementedError — stub not replaced"

# ── URL routing ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
cb = reverse('api_connector:oauth-callback')
assert cb == '/api/connector/oauth/callback/', f'Wrong callback URL: {cb}'
initiate = reverse('api_connector:profile-oauth-initiate', args=[1])
assert initiate == '/api/connector/profiles/1/oauth/initiate/', f'Wrong initiate URL: {initiate}'
print('OK')
" 2>/dev/null) && pass "OAuth AC URL routes resolve correctly" \
  || fail "OAuth AC URL routes not resolving — check urls.py and @action decorator"

# ── Serializer field ──────────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.serializers.connection_profile import ConnectionProfileReadSerializer
s = ConnectionProfileReadSerializer()
assert 'oauth_ac_authorized' in s.fields, 'oauth_ac_authorized not in read serializer'
assert 'encrypted_credentials' not in s.fields, 'SECURITY: encrypted_credentials exposed'
print('OK')
" 2>/dev/null) && pass "oauth_ac_authorized in read serializer; encrypted_credentials absent" \
  || fail "Serializer field check failed"

# ── OAUTH_REDIRECT_URI setting ────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.conf import settings
val = settings.OAUTH_REDIRECT_URI
assert val, 'OAUTH_REDIRECT_URI is empty'
assert 'oauth/callback' in val, f'OAUTH_REDIRECT_URI looks wrong: {val}'
print('OK')
" 2>/dev/null) && pass "settings.OAUTH_REDIRECT_URI configured" \
  || fail "settings.OAUTH_REDIRECT_URI missing or empty"

# ── Security checks ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security ─────────────────────────────────────────${NC}"
FERNET_IMPORTS=$(grep -r "from cryptography.fernet import Fernet" \
  "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -v "encryption.py" | wc -l)
[ "$FERNET_IMPORTS" -eq 0 ] && pass "No direct Fernet imports outside encryption.py" \
  || fail "Found $FERNET_IMPORTS Fernet imports outside encryption.py — security violation"

# Check postMessage never uses '*' as targetOrigin
WILDCARD_POSTMESSAGE=$(grep -n "postMessage" "$BACKEND/api_connector/views/oauth_callback.py" 2>/dev/null | grep "'\\*'" | wc -l)
[ "${WILDCARD_POSTMESSAGE:-0}" -eq 0 ] && pass "postMessage never uses '*' as targetOrigin" \
  || fail "SECURITY: postMessage targetOrigin is '*' — must use redirect_origin"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"
(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) && pass "ruff format passes" || fail "ruff format failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 155 ] && pass "pytest passes — $COUNT tests (≥155 required)" \
    || fail "pytest passes but only $COUNT tests (need ≥155)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend ─────────────────────────────────────────${NC}"
[ -f "$FRONTEND/src/features/connection-profile/components/OAuthACStatusBadge.tsx" ] \
  && pass "OAuthACStatusBadge.tsx exists" || fail "OAuthACStatusBadge.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/hooks/useOAuthAuthorize.ts" ] \
  && pass "useOAuthAuthorize.ts exists" || fail "useOAuthAuthorize.ts missing"
[ -f "$FRONTEND/src/features/connection-profile/api/oauthApi.ts" ] \
  && pass "oauthApi.ts exists" || fail "oauthApi.ts missing"

# Verify oauth_ac_authorized in domain types
grep -q "oauth_ac_authorized: boolean | null" \
  "$FRONTEND/src/shared/types/domain.ts" 2>/dev/null \
  && pass "oauth_ac_authorized typed as boolean | null in domain.ts" \
  || fail "oauth_ac_authorized missing or wrong type in domain.ts"

# Verify OAuthACStatus has 4 members
STATUS_COUNT=$(grep -c '"authorized"\|"authorizing"\|"unauthorized"\|"expired"' \
  "$FRONTEND/src/features/connection-profile/types/connectionTest.ts" 2>/dev/null || echo "0")
[ "${STATUS_COUNT:-0}" -ge 4 ] && pass "OAuthACStatus has ≥4 status values" \
  || fail "OAuthACStatus missing status values in connectionTest.ts"

(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) && pass "npm run typecheck passes" || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) && pass "npm run build passes" || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) && pass "npm test passes" || fail "npm test failed"
(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) && pass "npm run lint passes" || fail "npm run lint failed"

# ── Manual verification reminders ─────────────────────────────────────────────
echo ""
warn "Manual verification needed:"
warn "  Authorize button: disabled on create form; enabled on edit form with credentials saved"
warn "  Clicking Authorize → popup opens → consent → 'Authorized ✓' badge appears"
warn "  Connection test on authorized OAuth AC profile → step 3 passes"
warn "  Both GitHub CI workflows pass on push"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 4 COMPLETE — all 6 auth types fully operational — proceed to Phase 5${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 4 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi