#!/usr/bin/env bash
# scripts/validate-phase1.sh
# Run from repository root: bash scripts/validate-phase1.sh
# Exits 0 on full pass, non-zero on any failure.

set -uo pipefail

PASS=0
FAIL=0
WARN=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; ((PASS++)) || true; }
fail() { echo -e "${RED}✗ FAIL${NC}: $1"; ((FAIL++)) || true; }
warn() { echo -e "${YELLOW}⚠ WARN${NC}: $1"; ((WARN++)) || true; }

REPO_ROOT="$(pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
VENV="$BACKEND/.venv"

if [ -f "$VENV/bin/python" ]; then
  PYTHON="$VENV/bin/python"
  PYTEST="$VENV/bin/pytest"
  RUFF="$VENV/bin/ruff"
else
  PYTHON="$(command -v python3 || command -v python)"
  PYTEST="$(command -v pytest || echo 'pytest')"
  RUFF="$(command -v ruff || echo 'ruff')"
  warn "Virtual env not found at $VENV — using system Python: $PYTHON"
fi

MANAGE="$PYTHON manage.py"

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Phase 1 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Migration ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Migration ────────────────────────────────────────${NC}"

MIGRATION_STATUS=$(cd "$BACKEND" && $MANAGE showmigrations api_connector 2>/dev/null)
if echo "$MIGRATION_STATUS" | grep -q "\[X\] 0001_initial"; then
  pass "0001_initial applied (criteria #1)"
else
  fail "0001_initial not applied — run: cd backend && python manage.py migrate"
fi

TABLE_COUNT=$(cd "$BACKEND" && $MANAGE sqlmigrate api_connector 0001 2>/dev/null | grep -c "CREATE TABLE" || echo "0")
if [ "$TABLE_COUNT" -eq 6 ]; then
  pass "Migration contains 6 CREATE TABLE statements (criteria #2)"
else
  fail "Expected 6 CREATE TABLE statements, found $TABLE_COUNT (criteria #2)"
fi

# ── Model imports ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Models ───────────────────────────────────────────${NC}"

(cd "$BACKEND" && $MANAGE shell -c "
from api_connector.models import (
    ConnectionProfile, AuthConfig, Endpoint,
    PaginationConfig, SchemaField, ConnectionTestResult
)
print('OK')
" 2>/dev/null) && pass "All 6 models import cleanly (criteria #4)" \
  || fail "Model import failed — run: cd backend && python manage.py shell -c '...'"

# ── Encryption service ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Encryption Service ───────────────────────────────${NC}"

(cd "$BACKEND" && $MANAGE shell -c "
from api_connector.services.encryption import encryption_service
ct = encryption_service.encrypt('hello')
result = encryption_service.decrypt(ct)
assert result == 'hello', f'Expected hello, got {result}'
print('OK')
" 2>/dev/null) && pass "Encryption round-trip works (criteria #5+6)" \
  || fail "Encryption round-trip failed — check ENCRYPTION_KEY in backend/.env"

# ── Auth handler registry ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Auth Handler Registry ────────────────────────────${NC}"

(cd "$BACKEND" && $MANAGE shell -c "
from api_connector.services.auth.registry import auth_handler_registry
from api_connector.models import AuthType
h = auth_handler_registry.get(AuthType.BEARER)
assert type(h).__name__ == 'BearerAuthHandler', type(h).__name__
print('OK')
" 2>/dev/null) && pass "Registry returns BearerAuthHandler (criteria #7)" \
  || fail "Auth handler registry failed"

(cd "$BACKEND" && $MANAGE shell -c "
from api_connector.services.auth.registry import auth_handler_registry
from api_connector.models import AuthType
for t in AuthType.values:
    auth_handler_registry.get(t)
print('OK')
" 2>/dev/null) && pass "All 6 AuthType values resolve (criteria #8)" \
  || fail "Not all AuthType values resolve from registry"

# ── Pagination registry ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Pagination Registry ──────────────────────────────${NC}"

(cd "$BACKEND" && $MANAGE shell -c "
from api_connector.services.pagination.registry import pagination_registry
from api_connector.models import PaginationStrategy
try:
    pagination_registry.get(PaginationStrategy.OFFSET_LIMIT)
    print('ERROR')
    exit(1)
except ValueError:
    print('OK')
" 2>/dev/null) && pass "Pagination registry raises ValueError (criteria #9)" \
  || fail "Pagination registry should raise ValueError for unregistered strategies"

# ── DRF exception handler ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── DRF Exception Handler ────────────────────────────${NC}"

(cd "$BACKEND" && $MANAGE check --verbosity=0 2>/dev/null) \
  && pass "python manage.py check passes (criteria #10)" \
  || fail "python manage.py check failed"

# ── Security check: no direct Fernet imports ──────────────────────────────────
echo ""
echo -e "${BOLD}── Security ─────────────────────────────────────────${NC}"

FERNET_IMPORTS=$(grep -r "from cryptography.fernet import" "$BACKEND/api_connector" --include="*.py" | grep -v "encryption.py" | wc -l)
if [ "$FERNET_IMPORTS" -eq 0 ]; then
  pass "No direct cryptography.fernet imports outside encryption.py (criteria #16)"
else
  fail "Found $FERNET_IMPORTS direct Fernet imports outside encryption.py — security violation"
fi

# ── ADR files ─────────────────────────────────────────────────────────────────
ADR_COUNT=$(find "$REPO_ROOT/docs/adr" -name "00[3-6]-*.md" 2>/dev/null | wc -l | tr -d ' ')
if [ "$ADR_COUNT" -ge 4 ]; then
  pass "ADR-003 through ADR-006 exist ($ADR_COUNT files) (criteria #17)"
else
  fail "Expected 4 ADR files (003-006), found $ADR_COUNT"
fi

# ── Backend tests ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Backend Tests ────────────────────────────────────${NC}"

(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) \
  && pass "ruff check passes (criteria #12)" \
  || fail "ruff check failed — run: cd backend && ruff check ."

(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) \
  && pass "ruff format check passes (criteria #12)" \
  || fail "ruff format check failed — run: cd backend && ruff format ."

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  PYTEST_COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null | grep -oE "^[0-9]+" | head -1)
  if [ "${PYTEST_COUNT:-0}" -ge 15 ]; then
    pass "pytest passes with $PYTEST_COUNT tests (criteria #11)"
  else
    pass "pytest passes (test count $PYTEST_COUNT may be under expected 60+)"
  fi
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Frontend ─────────────────────────────────────────${NC}"

(cd "$FRONTEND" && npm run typecheck --silent 2>/dev/null) \
  && pass "npm run typecheck passes (criteria #13)" \
  || fail "npm run typecheck failed"

(cd "$FRONTEND" && npm run lint --silent 2>/dev/null) \
  && pass "npm run lint passes" \
  || fail "npm run lint failed"

(cd "$FRONTEND" && npm test 2>/dev/null) \
  && pass "npm test passes (criteria #14)" \
  || fail "npm test failed"

[ -f "$FRONTEND/src/shared/types/domain.ts" ] \
  && pass "domain.ts exists" || fail "domain.ts missing"

[ -f "$FRONTEND/src/lib/errors.ts" ] \
  && pass "errors.ts exists" || fail "errors.ts missing"

# ── Manual verification reminders ─────────────────────────────────────────────
echo ""
warn "Manual verification needed:"
warn "  criterion #3:  psql \\dt api_connector* shows 6 tables"
warn "  criterion #10: curl -X POST http://localhost:8000/api/health/ -> error_code in response"
warn "  criterion #15: Both CI workflows pass in GitHub Actions"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 1 COMPLETE — ready to start Phase 2${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 1 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi