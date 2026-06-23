#!/usr/bin/env bash
# scripts/validate-phase3.sh
# Run from repository root: bash scripts/validate-phase3.sh
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
echo -e "${BOLD}  Phase 3 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Migrations ────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Migrations ───────────────────────────────────────${NC}"
MIG=$(cd "$BACKEND" && $PYTHON manage.py showmigrations api_connector 2>/dev/null)
echo "$MIG" | grep -q "\[X\] 0001_initial" && pass "0001_initial applied" || fail "0001_initial missing"
echo "$MIG" | grep -q "\[X\] 0002_authconfig" && pass "0002_authconfig applied" || fail "0002 missing"
echo "$MIG" | grep -q "\[X\] 0003_oauth_token" && pass "0003_oauth_token applied" || fail "0003 not applied — run: python manage.py migrate"

# ── Table count ───────────────────────────────────────────────────────────────
TABLE_COUNT=$(cd "$BACKEND" && $PYTHON manage.py dbshell 2>/dev/null <<'SQL' | grep -c "api_connector_"
\dt api_connector*
SQL
)
[ "${TABLE_COUNT:-0}" -ge 7 ] && pass "7+ api_connector tables exist" || fail "Expected 7 tables, found ${TABLE_COUNT:-0}"

# ── Service imports ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Service Imports ──────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.connection_test import ConnectionTestService
from api_connector.services.oauth_cc_token import OAuthCCTokenService, OAuthCCTokenFetchError
print('OK')
" 2>/dev/null) && pass "ConnectionTestService and OAuthCCTokenService import cleanly" \
  || fail "Import error — check service files for syntax errors"

# ── OAuthCCAuthHandler no longer raises NotImplementedError ───────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
import httpx
from api_connector.services.auth.handlers.oauth_cc import OAuthCCAuthHandler
h = OAuthCCAuthHandler()
try:
    h.prepare_request(httpx.Request('GET', 'https://x.com'), {})
    print('ERROR')
    exit(1)
except ValueError:
    print('OK')
except NotImplementedError:
    print('STUB_STILL_PRESENT')
    exit(1)
" 2>/dev/null) && pass "OAuthCCAuthHandler raises ValueError (stub replaced)" \
  || fail "OAuthCCAuthHandler still raises NotImplementedError — stub not replaced"

# ── URL routing ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
url = reverse('api_connector:profile-test-connection', args=[1])
assert url == '/api/connector/profiles/1/test/', f'Wrong: {url}'
print('OK')
" 2>/dev/null) && pass "POST /api/connector/profiles/{id}/test/ URL resolves" \
  || fail "URL for profile-test-connection not found — check @action decorator"

# ── Security checks ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security ─────────────────────────────────────────${NC}"
FERNET_IMPORTS=$(grep -r "from cryptography.fernet import Fernet" "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -v "encryption.py" | wc -l)
[ "$FERNET_IMPORTS" -eq 0 ] && pass "No direct Fernet imports outside encryption.py" \
  || fail "Found $FERNET_IMPORTS Fernet imports outside encryption.py — security violation"

LOG_BODY=$(grep -r "body_sample\|response\.text" "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -i "logger\|log\." | wc -l)
[ "${LOG_BODY:-0}" -eq 0 ] && pass "Response body never logged (OWASP A09)" \
  || fail "body_sample or response.text found in log call — security violation"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"
(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) && pass "ruff format passes" || fail "ruff format failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 130 ] && pass "pytest passes — $COUNT tests (≥130 required)" \
    || fail "pytest passes but only $COUNT tests (need ≥130)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend ─────────────────────────────────────────${NC}"
[ -f "$FRONTEND/src/features/connection-profile/components/ConnectionTestModal.tsx" ] \
  && pass "ConnectionTestModal.tsx exists" || fail "ConnectionTestModal.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/components/StepResultItem.tsx" ] \
  && pass "StepResultItem.tsx exists" || fail "StepResultItem.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/types/connectionTest.ts" ] \
  && pass "connectionTest.ts TypeScript types exist" || fail "connectionTest.ts missing"

grep -q "MASK_DISPLAY" "$FRONTEND/src/features/connection-profile/components/SecretField.tsx" 2>/dev/null \
  && pass "SecretField MASK_DISPLAY constant unchanged" || warn "SecretField may have changed"

(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) && pass "npm run typecheck passes" || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) && pass "npm run build passes" || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) && pass "npm test passes" || fail "npm test failed"
(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) && pass "npm run lint passes" || fail "npm run lint failed"

# ── Manual steps reminder ─────────────────────────────────────────────────────
echo ""
warn "Manual verification needed:"
warn "  #16: POST /api/connector/profiles/{id}/test/ returns steps array, no credentials in response"
warn "  #17: Browser — Test Connection modal opens, progress simulation runs, results display"
warn "  #18: Both GitHub CI workflows pass on push"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 3 COMPLETE — Increment 1 ready — proceed to Phase 4 / Phase 5${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 3 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi