#!/usr/bin/env bash
# scripts/validate-phase2.sh
# Run from repository root: bash scripts/validate-phase2.sh
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

# Load nvm as a shell function (not a subshell) so nvm use modifies the current PATH
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -f "$REPO_ROOT/.nvmrc" ] && nvm use > /dev/null 2>&1 || true
NPM="$(command -v npm)"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Phase 2 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Migrations ────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Migrations ───────────────────────────────────────${NC}"

MIGRATIONS=$(cd "$BACKEND" && $PYTHON manage.py showmigrations api_connector 2>/dev/null)
echo "$MIGRATIONS" | grep -q "\[X\] 0001_initial" \
  && pass "0001_initial applied" || fail "0001_initial not applied"
echo "$MIGRATIONS" | grep -q "\[X\] 0002_authconfig" \
  && pass "0002_authconfig_credentials_summary applied" \
  || fail "0002 migration not applied — run: cd backend && python manage.py migrate"

# ── credentials_summary field ─────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.models import AuthConfig
fields = [f.name for f in AuthConfig._meta.get_fields()]
assert 'credentials_summary' in fields, f'Missing field. Fields: {fields}'
print('OK')
" 2>/dev/null) && pass "credentials_summary field exists on AuthConfig" \
  || fail "credentials_summary missing from AuthConfig"

# ── Serializer security ───────────────────────────────────────────────────────
echo -e "\n${BOLD}── Serializer Security ──────────────────────────────${NC}"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.serializers.connection_profile import ConnectionProfileReadSerializer
s = ConnectionProfileReadSerializer()
assert 'encrypted_credentials' not in s.fields, \
  f'SECURITY: encrypted_credentials in read serializer: {list(s.fields.keys())}'
assert 'credentials_summary' in s.fields
print('OK')
" 2>/dev/null) && pass "encrypted_credentials absent from read serializer" \
  || fail "SECURITY VIOLATION: encrypted_credentials in read serializer"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"

(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) \
  && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) \
  && pass "ruff format check passes" || fail "ruff format check failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 90 ] \
    && pass "pytest passes — $COUNT tests (≥90 required)" \
    || fail "pytest passes but only $COUNT tests (need ≥90)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── URL routing ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
url = reverse('api_connector:profile-list')
assert url == '/api/connector/profiles/', f'Wrong URL: {url}'
print('OK')
" 2>/dev/null) && pass "Profile list URL resolves to /api/connector/profiles/" \
  || fail "Profile list URL incorrect — check DefaultRouter registration"

# ── API endpoint smoke test ───────────────────────────────────────────────────
echo -e "\n${BOLD}── API Smoke Test ───────────────────────────────────${NC}"

(pgrep -f "runserver" > /dev/null 2>&1) && DJANGO_RUNNING=true || DJANGO_RUNNING=false

if $DJANGO_RUNNING; then
  RESPONSE=$(curl -s http://localhost:8000/api/connector/profiles/ 2>/dev/null)
  if echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list)" 2>/dev/null; then
    pass "GET /api/connector/profiles/ returns JSON array"
    echo "$RESPONSE" | grep -q "blob" && fail "SECURITY: 'blob' found in list response" || pass "No 'blob' in list response"
  else
    fail "GET /api/connector/profiles/ did not return a JSON array"
  fi
else
  warn "Django server not running — start with: cd backend && python manage.py runserver"
  warn "Then re-run this script for API smoke tests"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend ─────────────────────────────────────────${NC}"

[ -f "$FRONTEND/src/features/connection-profile/pages/ProfileListPage.tsx" ] \
  && pass "ProfileListPage.tsx exists" || fail "ProfileListPage.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/pages/ProfileFormPage.tsx" ] \
  && pass "ProfileFormPage.tsx exists" || fail "ProfileFormPage.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/components/SecretField.tsx" ] \
  && pass "SecretField.tsx exists" || fail "SecretField.tsx missing"
[ -f "$FRONTEND/src/features/connection-profile/components/auth-fields/index.ts" ] \
  && pass "auth-fields/index.ts exists (AUTH_FIELDS_COMPONENT_MAP)" \
  || fail "auth-fields/index.ts missing"

grep -q "MASK_DISPLAY.*=.*\"••••••••\"" "$FRONTEND/src/features/connection-profile/components/SecretField.tsx" 2>/dev/null \
  && pass "SecretField uses hardcoded MASK_DISPLAY constant" \
  || fail "SecretField MASK_DISPLAY may be derived from value — security check"

grep -q '"react-router-dom"' "$FRONTEND/package.json" \
  && pass "react-router-dom in package.json" || fail "react-router-dom missing from package.json"

(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) \
  && pass "npm run typecheck passes" || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) \
  && pass "npm run build passes" || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) \
  && pass "npm test passes" || fail "npm test failed"

# ── Security audit ────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security Audit ───────────────────────────────────${NC}"

FERNET_IMPORTS=$(grep -r "from cryptography.fernet import Fernet" "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -v "encryption.py" | wc -l)
[ "$FERNET_IMPORTS" -eq 0 ] \
  && pass "No direct Fernet imports outside encryption.py" \
  || fail "Found $FERNET_IMPORTS Fernet import(s) outside encryption.py — security violation"

grep -q "decrypt" "$BACKEND/api_connector/serializers/connection_profile.py" 2>/dev/null \
  && DECRYPT_IN_READ=$(grep -n "decrypt" "$BACKEND/api_connector/serializers/connection_profile.py") \
  && grep -q "get_credentials_summary" <<< "$DECRYPT_IN_READ" \
  && fail "ANTI-PATTERN #4: decrypt called in get_credentials_summary — read from plaintext field instead" \
  || pass "get_credentials_summary reads plaintext field (no decrypt)"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 2 COMPLETE — ready to start Phase 3${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 2 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi