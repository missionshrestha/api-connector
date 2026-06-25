#!/usr/bin/env bash
# scripts/validate-phase8.sh
# Run from repository root: bash scripts/validate-phase8.sh
# The final production-readiness gate for the API Connector.
# Exits 0 when the system is cleared for production deployment.

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
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Phase 8 — Production Readiness Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"

# ── Critical Bug Fixes ────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Critical Bug Fixes ───────────────────────────────────────${NC}"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.exceptions import custom_exception_handler
from api_connector.services.oauth_ac_exceptions import OAuthACReauthorizationRequired, REASON_NO_TOKEN
r = custom_exception_handler(OAuthACReauthorizationRequired(REASON_NO_TOKEN, 'No token found.'), {})
assert r.status_code == 401, f'Expected 401, got {r.status_code}'
assert r.data['error_code'] == 'API_CONN_041'
print('OK')
" 2>/dev/null) && pass "OAuthACReauthorizationRequired → HTTP 401 (not 500) — Bug P8.B-06 fixed" \
  || fail "OAuthACReauthorizationRequired still returns 500 — apply fix in exceptions.py"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.views.endpoint import EndpointViewSet
import inspect
src = inspect.getsource(EndpointViewSet.preview)
assert 'PaginationEngineError' in src, 'PaginationEngineError not in preview except block'
print('OK')
" 2>/dev/null) && pass "PaginationEngineError caught in preview() view (not 500) — Bug P8.C-02 fixed" \
  || fail "PaginationEngineError not in preview() except block — non-JSON APIs will return 500"

# ── Security Enforcement ──────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security Enforcement ─────────────────────────────────────${NC}"

FERNET_COUNT=$(grep -r "from cryptography.fernet import Fernet" \
  "$BACKEND/api_connector" --include="*.py" 2>/dev/null | grep -v "encryption.py" | wc -l | tr -d ' ')
[ "${FERNET_COUNT:-0}" -eq 0 ] && pass "No direct Fernet imports outside encryption.py (ADR-005)" \
  || fail "Found $FERNET_COUNT direct Fernet import(s) outside encryption.py — ADR-005 violation"

grep -q "No direct Fernet" "$REPO_ROOT/.github/workflows/backend-ci.yml" 2>/dev/null \
  && pass "Fernet import enforcement step in backend-ci.yml (P8.B-05)" \
  || fail "Fernet import enforcement step missing from backend-ci.yml"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.ssrf import validate_url_for_ssrf, SSRFProtectionError
# Verify SSRF is importable and default-disabled
validate_url_for_ssrf('http://192.168.1.1/api')  # Should NOT raise (default disabled)
print('OK')
" 2>/dev/null) && pass "SSRF protection utility available; default disabled (safe for dev)" \
  || fail "SSRF protection utility missing — create api_connector/services/ssrf.py"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.conf import settings
assert hasattr(settings, 'SSRF_PROTECTION_ENABLED'), 'SSRF_PROTECTION_ENABLED missing from settings'
print('OK')
" 2>/dev/null) && pass "SSRF_PROTECTION_ENABLED setting present in settings.py" \
  || fail "SSRF_PROTECTION_ENABLED missing from settings.py"

# ── Error Messages Audit ──────────────────────────────────────────────────────
echo -e "\n${BOLD}── Error Messages Audit ─────────────────────────────────────${NC}"

# NOTE: `grep -c` exits 1 on zero matches; `|| true` swallows that without
# appending a spurious second "0" line (the old `|| echo 0` produced "0\n0",
# which broke the integer test below and caused a false FAIL).
REFUSED=$(grep -c "Connection refused" "$BACKEND/api_connector/services/plain_english_errors.py" 2>/dev/null || true)
[ "${REFUSED:-0}" -eq 0 ] && pass "Error messages: 'Connection refused' replaced with plain English" \
  || fail "plain_english_errors.py still contains 'Connection refused' — update to 'Could not connect to'"

DECRYPTED=$(grep -c "decrypted\." "$BACKEND/api_connector/services/plain_english_errors.py" 2>/dev/null || true)
[ "${DECRYPTED:-0}" -eq 0 ] && pass "Error messages: 'decrypted' technical term removed" \
  || fail "plain_english_errors.py still contains 'decrypted' — update to plain English"

# ── Management Commands ───────────────────────────────────────────────────────
echo -e "\n${BOLD}── Management Commands ──────────────────────────────────────${NC}"

(cd "$BACKEND" && $PYTHON manage.py cleanup_oauth_ac_states > /dev/null 2>&1) \
  && pass "cleanup_oauth_ac_states command runs without error" \
  || fail "cleanup_oauth_ac_states command fails — check management/commands/cleanup_oauth_ac_states.py"

(cd "$BACKEND" && $PYTHON manage.py help rotate_encryption_key > /dev/null 2>&1) \
  && pass "rotate_encryption_key command is registered and documented" \
  || fail "rotate_encryption_key command missing — create management/commands/rotate_encryption_key.py"

(cd "$BACKEND" && $PYTHON manage.py help benchmark > /dev/null 2>&1) \
  && pass "benchmark command is registered" \
  || fail "benchmark command missing — create management/commands/benchmark.py"

# ── Django System Check ───────────────────────────────────────────────────────
echo -e "\n${BOLD}── Django System Check ──────────────────────────────────────${NC}"

(cd "$BACKEND" && $PYTHON manage.py check --verbosity=0 2>/dev/null) \
  && pass "python manage.py check exits 0 (no Django configuration issues)" \
  || fail "python manage.py check failed — system configuration issue"

# ── Backend Tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────────────${NC}"

(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) && pass "ruff format passes" || fail "ruff format failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 280 ] \
    && pass "pytest passes — $COUNT tests collected (≥280 required)" \
    || warn "pytest passes but only $COUNT tests (target ≥280 — edge case tests may be incomplete)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Documentation ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Documentation ────────────────────────────────────────────${NC}"

DOC_COUNT=$(git -C "$REPO_ROOT" ls-files docs/security-audit.md docs/operations.md docs/benchmark-results.md 2>/dev/null | wc -l | tr -d ' ')
[ "${DOC_COUNT:-0}" -ge 2 ] && pass "$DOC_COUNT/3 documentation files tracked in git" \
  || fail "Documentation files missing — need docs/security-audit.md, docs/operations.md, docs/benchmark-results.md"

AUDIT_LINES=$(wc -l < "$REPO_ROOT/docs/security-audit.md" 2>/dev/null || echo "0")
[ "${AUDIT_LINES:-0}" -ge 80 ] && pass "docs/security-audit.md ≥ 80 lines ($AUDIT_LINES lines)" \
  || fail "docs/security-audit.md too short ($AUDIT_LINES lines, need ≥80) — complete the security audit"

OPS_LINES=$(wc -l < "$REPO_ROOT/docs/operations.md" 2>/dev/null || echo "0")
[ "${OPS_LINES:-0}" -ge 60 ] && pass "docs/operations.md ≥ 60 lines ($OPS_LINES lines)" \
  || fail "docs/operations.md too short ($OPS_LINES lines, need ≥60) — complete the operations runbook"

grep -q "SSRF_PROTECTION_ENABLED" "$REPO_ROOT/backend/.env.example" 2>/dev/null \
  && pass "SSRF_PROTECTION_ENABLED documented in .env.example" \
  || fail "SSRF_PROTECTION_ENABLED missing from backend/.env.example"

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend ─────────────────────────────────────────────────${NC}"

SCHEMA_TREE_TEST="$FRONTEND/src/features/schema-explorer/components/__tests__/SchemaExplorerTree.dom.test.tsx"
[ -f "$SCHEMA_TREE_TEST" ] && pass "SchemaExplorerTree DOM count test exists" \
  || fail "SchemaExplorerTree.dom.test.tsx missing — create virtual scroll DOM test"

grep -q "data-schema-field-row" \
  "$FRONTEND/src/features/schema-explorer/components/SchemaFieldRow.tsx" 2>/dev/null \
  && pass "SchemaFieldRow has data-schema-field-row attribute (required for DOM count test)" \
  || fail "data-schema-field-row attribute missing from SchemaFieldRow.tsx"

(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) && pass "npm run typecheck passes" || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) && pass "npm run build passes" || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) && pass "npm test passes" || fail "npm test failed"
(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) && pass "npm run lint passes" || fail "npm run lint failed"

# ── ADR Count ─────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Architecture Decision Records ────────────────────────────${NC}"

ADR_COUNT=$(find "$REPO_ROOT/docs/adr" -name "0*.md" 2>/dev/null | wc -l | tr -d ' ')
[ "${ADR_COUNT:-0}" -ge 10 ] && pass "ADR directory has $ADR_COUNT decision records (Phases 0–8)" \
  || warn "Only $ADR_COUNT ADR files found (expected ≥10 from all phases)"

# ── Manual Reminders ──────────────────────────────────────────────────────────
echo ""
warn "Manual production-readiness checks (not automatable):"
warn "  1. Live end-to-end test: profile → endpoint → inference → alias → preview → export CSV"
warn "  2. Verify CSV export has alias-named headers"
warn "  3. Verify 'Connection Profiles' page loads in < 500ms with 50+ profiles"
warn "  4. Both GitHub CI workflows pass on current branch"
warn "  5. Set SSRF_PROTECTION_ENABLED=True in shared/cloud environments"
warn "  6. Set SECURE_SSL_REDIRECT=True in production"
warn "  7. Branch protection configured on 'main' branch"

# ── Final Summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ READY FOR PRODUCTION — Increment 4 complete${NC}"
  echo ""
  echo -e "  System cleared for production deployment."
  echo -e "  Before deploying:"
  echo -e "    • Set SECURE_SSL_REDIRECT=True"
  echo -e "    • Set SSRF_PROTECTION_ENABLED=True in shared environments"
  echo -e "    • Configure branch protection on main"
  echo -e "    • Store ENCRYPTION_KEY in a secrets manager"
  exit 0
else
  echo -e "${RED}${BOLD}✗ NOT PRODUCTION-READY — fix ${FAIL} failure(s) above${NC}"
  exit 1
fi