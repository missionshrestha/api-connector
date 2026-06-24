#!/usr/bin/env bash
# scripts/validate-phase6.sh
# Run from repository root: bash scripts/validate-phase6.sh
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
echo -e "${BOLD}  Phase 6 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Settings ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Settings ─────────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.conf import settings
assert settings.SCHEMA_INFERENCE_MAX_DEPTH == 10, \
    f'Expected 10, got {settings.SCHEMA_INFERENCE_MAX_DEPTH}'
print('OK')
" 2>/dev/null) && pass "SCHEMA_INFERENCE_MAX_DEPTH = 10 (criteria #1)" \
  || fail "SCHEMA_INFERENCE_MAX_DEPTH missing or wrong — check settings.py"

# ── Engine importable ─────────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.schema_inference import SchemaInferenceEngine
print('OK')
" 2>/dev/null) && pass "SchemaInferenceEngine importable (criteria #2)" \
  || fail "SchemaInferenceEngine import failed — check schema_inference/__init__.py"

# ── Critical edge cases (logic, not just import) ──────────────────────────────
echo -e "\n${BOLD}── Critical Edge Cases ──────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.schema_inference.engine import _infer_type_from_values
assert _infer_type_from_values([True, False]) == 'boolean', \
    'FAIL: bool classified as integer — bool check is after int check'
print('OK')
" 2>/dev/null) && pass "_infer_type_from_values([True, False]) → 'boolean' (criteria #11)" \
  || fail "CRITICAL: bool/int ordering broken — [True, False] returns 'integer' not 'boolean'"

(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.schema_inference.engine import _infer_type_from_values
assert _infer_type_from_values([0, 1, 2.5]) == 'float', \
    'FAIL: int+float not widening to float'
print('OK')
" 2>/dev/null) && pass "_infer_type_from_values([0, 1, 2.5]) → 'float' widening (criteria #12)" \
  || fail "CRITICAL: int+float not widening to float — check _infer_type_from_values"

# ── URL routing ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
tests = [
    ('api_connector:endpoint-schema-infer',
     {'profile_pk':1,'pk':1},
     '/api/connector/profiles/1/endpoints/1/schema/infer/'),
    ('api_connector:endpoint-schema-fields',
     {'profile_pk':1,'pk':1},
     '/api/connector/profiles/1/endpoints/1/schema/fields/'),
    ('api_connector:endpoint-schema-fields-bulk-update',
     {'profile_pk':1,'pk':1},
     '/api/connector/profiles/1/endpoints/1/schema/fields/bulk-update/'),
    ('api_connector:endpoint-schema-field-update',
     {'profile_pk':1,'pk':1,'field_pk':5},
     '/api/connector/profiles/1/endpoints/1/schema/fields/5/'),
]
for name, kwargs, expected in tests:
    url = reverse(name, kwargs=kwargs)
    assert url == expected, f'{name}: got {url!r}'
print('OK')
" 2>/dev/null) && pass "All 4 schema action URLs resolve correctly (criteria #3–5)" \
  || fail "Schema URL routing broken — check @action url_name params in EndpointViewSet"

# ── Security ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security ─────────────────────────────────────────${NC}"
FERNET_COUNT=$(grep -r "from cryptography.fernet import Fernet" \
  "$BACKEND/api_connector" --include="*.py" 2>/dev/null \
  | grep -v "encryption.py" | wc -l | tr -d ' ')
[ "${FERNET_COUNT:-0}" -eq 0 ] \
  && pass "No direct Fernet imports outside encryption.py (criteria #15)" \
  || fail "Found $FERNET_COUNT Fernet imports outside encryption.py"

# sample_value never logged
SAMPLE_LOG=$(grep -r "sample_value" "$BACKEND/api_connector" --include="*.py" 2>/dev/null \
  | grep -i "logger\|log\." | wc -l | tr -d ' ')
[ "${SAMPLE_LOG:-0}" -eq 0 ] \
  && pass "sample_value never logged (potential PII protection)" \
  || fail "sample_value appears in a log call — check for PII leakage"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"
(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) \
  && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) \
  && pass "ruff format passes" || fail "ruff format failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null \
    | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 240 ] \
    && pass "pytest passes — $COUNT tests (≥240 required) (criteria #16–17)" \
    || fail "pytest passes but only $COUNT tests (need ≥240)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Frontend files ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend Files ───────────────────────────────────${NC}"
REQUIRED=(
  "src/features/schema-explorer/pages/SchemaExplorerPage.tsx"
  "src/features/schema-explorer/components/SchemaExplorerTree.tsx"
  "src/features/schema-explorer/components/TypeBadge.tsx"
  "src/features/schema-explorer/components/NullPercentageBar.tsx"
  "src/features/schema-explorer/components/AliasInput.tsx"
  "src/features/schema-explorer/components/SchemaFieldRow.tsx"
  "src/features/schema-explorer/components/RerunInferenceDialog.tsx"
  "src/features/schema-explorer/hooks/useSchemaFields.ts"
  "src/features/schema-explorer/api/schemaApi.ts"
)
ALL_PRESENT=true
for f in "${REQUIRED[@]}"; do
  if [ ! -f "$FRONTEND/$f" ]; then
    fail "Missing: frontend/$f"
    ALL_PRESENT=false
  fi
done
[ "$ALL_PRESENT" = true ] && pass "All required schema-explorer frontend files exist"

# SCHEMA_QUERY_KEY must be a function
grep -q "SCHEMA_QUERY_KEY = (profileId" \
  "$FRONTEND/src/features/schema-explorer/hooks/useSchemaFields.ts" 2>/dev/null \
  && pass "SCHEMA_QUERY_KEY is a function (per-endpoint cache isolation)" \
  || fail "SCHEMA_QUERY_KEY must be a function '(profileId, endpointId) => ...' not a constant"

# Virtualizer must use react-virtual
grep -q "useVirtualizer" \
  "$FRONTEND/src/features/schema-explorer/components/SchemaExplorerTree.tsx" 2>/dev/null \
  && pass "SchemaExplorerTree uses useVirtualizer from @tanstack/react-virtual" \
  || fail "SchemaExplorerTree missing useVirtualizer — 200+ field performance not guaranteed"

# Fixed-height scroll container
grep -q "height.*600px\|height.*500px" \
  "$FRONTEND/src/features/schema-explorer/components/SchemaExplorerTree.tsx" 2>/dev/null \
  && pass "SchemaExplorerTree has explicit fixed-height scroll container" \
  || fail "CRITICAL: Missing fixed height on scroll container — virtualizer will render nothing"

# estimateSize: () => 48
grep -q "estimateSize.*48\|estimateSize.*() => 48" \
  "$FRONTEND/src/features/schema-explorer/components/SchemaExplorerTree.tsx" 2>/dev/null \
  && pass "virtualizer estimateSize is 48 (matches h-12 row height)" \
  || fail "estimateSize not set or not 48 — row layout may be broken"

# @tanstack/react-virtual in package.json
grep -q '"@tanstack/react-virtual"' "$FRONTEND/package.json" 2>/dev/null \
  && pass "@tanstack/react-virtual in package.json (criteria #19)" \
  || fail "@tanstack/react-virtual missing from package.json"

# Schema route in App.tsx
grep -q "endpointId/schema" "$FRONTEND/src/App.tsx" 2>/dev/null \
  && pass "Schema route present in App.tsx (criteria #21)" \
  || fail "Schema route missing from App.tsx"

# Schema link on EndpointListPage
grep -q "/schema" "$FRONTEND/src/features/endpoint/pages/EndpointListPage.tsx" 2>/dev/null \
  && pass "Schema link in EndpointListPage (criteria #22)" \
  || fail "Schema navigation link missing from EndpointListPage"

# alias blur-save pattern check
grep -q "onBlur.*attemptSave\|onBlur={attemptSave}" \
  "$FRONTEND/src/features/schema-explorer/components/AliasInput.tsx" 2>/dev/null \
  && pass "AliasInput implements blur-save pattern" \
  || fail "AliasInput missing blur-save — check onBlur handler"

# Frontend toolchain
(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) \
  && pass "npm run typecheck passes (criteria #20)" \
  || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) \
  && pass "npm run build passes (criteria #20)" \
  || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) \
  && pass "npm test passes (criteria #20)" \
  || fail "npm test failed"
(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) \
  && pass "npm run lint passes" \
  || fail "npm run lint failed"

# ── Manual verification reminders ─────────────────────────────────────────────
echo ""
warn "Manual verification needed:"
warn "  criteria #6:  POST /schema/infer/ on live endpoint → 200 with field list"
warn "  criteria #7:  GET /schema/fields/ → includes stale fields"
warn "  criteria #8:  duplicate alias PATCH → 400 with API_CONN_054"
warn "  criteria #9:  cross-endpoint field update → 404"
warn "  criteria #10: bulk-update include_all:false → all fields excluded"
warn "  criteria #13: re-run preserves alias on existing field"
warn "  criteria #14: disappeared field → stale=True in DB"
warn "  criteria #23: 200+ fields in Explorer — verify ≤20 DOM rows at any scroll pos"
warn "  criteria #24: re-run dialog shown when aliases/overrides/exclusions exist"
warn "  criteria #25: Both GitHub CI workflows pass on push"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 6 COMPLETE — ready to start Phase 7${NC}"
  echo ""
  echo -e "  Phase 7 (Data Preview) can now read:"
  echo -e "  ${BOLD}SchemaField.objects.filter(endpoint=ep, include=True)${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 6 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi