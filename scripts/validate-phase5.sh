#!/usr/bin/env bash
# scripts/validate-phase5.sh
# Run from repository root: bash scripts/validate-phase5.sh
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
echo -e "${BOLD}  Phase 5 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── No new migrations ─────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Migrations ───────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py makemigrations api_connector --check 2>/dev/null) \
  && pass "No new migrations — Phase 5 adds no new models (criteria #1)" \
  || fail "Unexpected pending migrations detected — check models for accidental changes"

# ── PaginationRegistry populated ──────────────────────────────────────────────
echo -e "\n${BOLD}── PaginationRegistry ───────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.pagination.registry import pagination_registry
from api_connector.models import PaginationStrategy
params = {
    'offset_param': 'offset', 'limit_param': 'limit', 'page_size': 10,
    'page_param': 'page', 'page_size_param': 'per_page',
    'cursor_request_param': 'after', 'cursor_response_path': 'meta.cursor',
    'next_url_response_path': 'links.next',
}
for s in PaginationStrategy.values:
    h = pagination_registry.get(s, params=params)
    assert h is not None, f'Registry returned None for {s}'
print('OK')
" 2>/dev/null) && pass "All 6 strategies registered in PaginationRegistry (criteria #2)" \
  || fail "PaginationRegistry still raises ValueError for some strategies — check registry.py"

# ── OffsetLimit == page_size edge case ────────────────────────────────────────
echo -e "\n${BOLD}── Critical Edge Cases ──────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.pagination.strategies import OffsetLimitStrategy
from api_connector.services.pagination.types import PaginatedResponse
ol = OffsetLimitStrategy({'offset_param': 'offset', 'limit_param': 'limit', 'page_size': 20})
ol.initial_params()
resp = PaginatedResponse(
    raw_headers={}, raw_body={},
    records=list(range(20)), page_count=1, total_fetched=20
)
result = ol.next_params(resp)
assert result is not None, 'FAIL: OffsetLimit incorrectly stops at == page_size'
assert result['offset'] == 20
print('OK')
" 2>/dev/null) && pass "OffsetLimit == page_size correctly continues (NOT stops) — criteria #11" \
  || fail "CRITICAL: OffsetLimit stops at == page_size — silently drops last page when total_records % page_size == 0"

# ── Cursor == 0 edge case ─────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.pagination.strategies import CursorStrategy
from api_connector.services.pagination.types import PaginatedResponse
cs = CursorStrategy({'cursor_request_param': 'after', 'cursor_response_path': 'cursor'})
resp = PaginatedResponse(
    raw_headers={}, raw_body={'cursor': 0},
    records=[{'id': 1}], page_count=1, total_fetched=1
)
result = cs.next_params(resp)
assert result is not None, 'FAIL: cursor=0 incorrectly stops pagination'
assert result['after'] == 0
print('OK')
" 2>/dev/null) && pass "Cursor == 0 correctly continues (integer 0 is valid cursor) — criteria #12" \
  || fail "CRITICAL: cursor=0 stops pagination — integer 0 is a valid cursor value"

# ── URL routing ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
tests = [
    ('api_connector:endpoint-list',
     {'profile_pk': 1},
     '/api/connector/profiles/1/endpoints/'),
    ('api_connector:endpoint-pagination',
     {'profile_pk': 1, 'pk': 1},
     '/api/connector/profiles/1/endpoints/1/pagination/'),
    ('api_connector:endpoint-detect-data-root',
     {'profile_pk': 1, 'pk': 1},
     '/api/connector/profiles/1/endpoints/1/detect-data-root/'),
]
for name, kwargs, expected in tests:
    url = reverse(name, kwargs=kwargs)
    assert url == expected, f'{name}: got {url!r}, expected {expected!r}'
print('OK')
" 2>/dev/null) && pass "All 3 endpoint URL routes resolve correctly (criteria #3–5)" \
  || fail "Endpoint URL routing broken — check urls.py second router and @action decorators"

python manage.py check exits cleanly
(cd "$BACKEND" && $PYTHON manage.py check --verbosity=0 2>/dev/null) \
  && pass "python manage.py check passes" \
  || fail "manage.py check failed — fix before running tests"

# ── PaginationEngine is a generator ──────────────────────────────────────────
echo -e "\n${BOLD}── PaginationEngine ─────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.pagination.engine import PaginationEngine, PaginationEngineError
import inspect
src = inspect.getsource(PaginationEngine.paginate)
assert 'yield' in src, 'paginate() must contain yield — it must be a generator'
print('OK')
" 2>/dev/null) && pass "PaginationEngine.paginate() is a generator (contains yield) — ADR-010" \
  || fail "PaginationEngine import error or paginate() is missing yield keyword"

# ── Utils importable ──────────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON -c "
from api_connector.services.pagination.utils import (
    extract_records_at_path, build_request_url, detect_data_root
)
# Quick smoke tests
assert extract_records_at_path(None, 'data') == []
assert build_request_url('https://api.com/', '/items', {}) == 'https://api.com/items'
assert detect_data_root({'data': [{'id': 1}]}) == ['data']
print('OK')
" 2>/dev/null) && pass "pagination utils (extract_records_at_path, build_request_url, detect_data_root) work" \
  || fail "pagination utils import or smoke test failed — check utils.py"

# ── Serializers importable ────────────────────────────────────────────────────
echo -e "\n${BOLD}── Serializers ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.serializers.endpoint import (
    EndpointReadSerializer, EndpointCreateSerializer, EndpointUpdateSerializer
)
from api_connector.serializers.pagination_config import (
    PaginationConfigUpdateSerializer, STRATEGY_PARAMS_SERIALIZER_MAP
)
from api_connector.models import PaginationStrategy
assert set(STRATEGY_PARAMS_SERIALIZER_MAP.keys()) == set(PaginationStrategy.values), \
    f'Missing strategies in STRATEGY_PARAMS_SERIALIZER_MAP'
s = EndpointReadSerializer()
assert 'detected_path_variables' in s.fields
assert 'has_pagination_config' in s.fields
print('OK')
" 2>/dev/null) && pass "Endpoint and PaginationConfig serializers import and have required fields" \
  || fail "Serializer import failed — check serializers/endpoint.py and serializers/pagination_config.py"

# ── Security checks ───────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security ─────────────────────────────────────────${NC}"
FERNET_COUNT=$(grep -r "from cryptography.fernet import Fernet" \
  "$BACKEND/api_connector" --include="*.py" 2>/dev/null \
  | grep -v "encryption.py" | wc -l | tr -d ' ')
[ "${FERNET_COUNT:-0}" -eq 0 ] \
  && pass "No direct Fernet imports outside encryption.py (criteria #16)" \
  || fail "Found $FERNET_COUNT direct Fernet import(s) outside encryption.py — security violation (ADR-005)"

# data_root_path path-traversal validation
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.serializers.endpoint import EndpointCreateSerializer
s = EndpointCreateSerializer(data={
    'name': 'Test', 'path': '/api', 'method': 'GET',
    'data_root_path': '../../etc/passwd',
})
assert not s.is_valid(), 'FAIL: path-traversal data_root_path must be rejected'
assert 'data_root_path' in s.errors
print('OK')
" 2>/dev/null) && pass "Path-traversal data_root_path correctly rejected (OWASP A03)" \
  || fail "SECURITY: path-traversal data_root_path not rejected by EndpointCreateSerializer"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"
(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) \
  && pass "ruff check passes (criteria #15)" \
  || fail "ruff check failed — run: cd backend && ruff check ."

(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) \
  && pass "ruff format check passes (criteria #15)" \
  || fail "ruff format check failed — run: cd backend && ruff format ."

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null \
    | grep -oE "^[0-9]+" | head -1 || echo "0")
  if [ "${COUNT:-0}" -ge 210 ]; then
    pass "pytest passes — $COUNT tests collected (≥210 required) (criteria #13–14)"
  else
    fail "pytest passes but only $COUNT tests collected — need ≥210 (missing test files?)"
  fi
else
  fail "pytest failed — run: cd backend && pytest -v for details"
fi

# ── Frontend ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend ─────────────────────────────────────────${NC}"

# Check key files exist
REQUIRED_FILES=(
  "src/features/endpoint/pages/EndpointListPage.tsx"
  "src/features/endpoint/pages/EndpointFormPage.tsx"
  "src/features/endpoint/components/PaginationStrategySelector.tsx"
  "src/features/endpoint/components/DataRootPathInput.tsx"
  "src/features/endpoint/components/PathVariableEditor.tsx"
  "src/features/endpoint/components/QueryParamEditor.tsx"
  "src/features/endpoint/components/EndpointHeadersEditor.tsx"
  "src/features/endpoint/hooks/useEndpoints.ts"
  "src/features/endpoint/api/endpointApi.ts"
  "src/features/endpoint/api/paginationApi.ts"
  "src/features/endpoint/schemas/endpointSchema.ts"
  "src/features/endpoint/schemas/paginationConfigSchema.ts"
)
ALL_FILES_PRESENT=true
for f in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$FRONTEND/$f" ]; then
    fail "Missing: frontend/$f"
    ALL_FILES_PRESENT=false
  fi
done
[ "$ALL_FILES_PRESENT" = true ] && pass "All required endpoint feature files exist"

# ENDPOINT_QUERY_KEY must be a function (not a constant)
if grep -q "ENDPOINT_QUERY_KEY = (profileId" "$FRONTEND/src/features/endpoint/hooks/useEndpoints.ts" 2>/dev/null; then
  pass "ENDPOINT_QUERY_KEY is a function (profile-scoped cache isolation correct)"
else
  fail "ENDPOINT_QUERY_KEY must be a function '(profileId: number) => ...' not a constant array"
fi

# Strategy selector must clear strategy_params on switch
if grep -q "strategy_params: {}" "$FRONTEND/src/features/endpoint/components/PaginationStrategySelector.tsx" 2>/dev/null; then
  pass "PaginationStrategySelector clears strategy_params on strategy switch"
else
  fail "PaginationStrategySelector may not clear strategy_params on switch — check handleStrategyChange"
fi

# Auto-detect button disabled check
if grep -q "canAutoDetect" "$FRONTEND/src/features/endpoint/components/DataRootPathInput.tsx" 2>/dev/null; then
  pass "DataRootPathInput has canAutoDetect guard (disabled on create form)"
else
  fail "DataRootPathInput missing canAutoDetect guard — Auto-Detect must be disabled on create form"
fi

# type="button" on editor components
QP_BUTTONS=$(grep -c 'type="button"' "$FRONTEND/src/features/endpoint/components/QueryParamEditor.tsx" 2>/dev/null || echo "0")
[ "${QP_BUTTONS:-0}" -ge 2 ] \
  && pass "QueryParamEditor has type=\"button\" on action buttons (prevents accidental form submit)" \
  || fail "QueryParamEditor buttons missing type=\"button\" — will accidentally submit parent form"

# oauth_ac_authorized still in domain types (not regressed)
if grep -q "oauth_ac_authorized" "$FRONTEND/src/shared/types/domain.ts" 2>/dev/null; then
  pass "oauth_ac_authorized still present in domain.ts (Phase 4 not regressed)"
else
  warn "oauth_ac_authorized missing from domain.ts — check if Phase 4 types were accidentally removed"
fi

# Endpoint and PaginationConfig types present
if grep -q "detected_path_variables: string\[\]" "$FRONTEND/src/shared/types/domain.ts" 2>/dev/null; then
  pass "Endpoint.detected_path_variables typed as string[] in domain.ts"
else
  fail "Endpoint.detected_path_variables missing or wrong type in domain.ts"
fi

if grep -q "has_pagination_config: boolean" "$FRONTEND/src/shared/types/domain.ts" 2>/dev/null; then
  pass "Endpoint.has_pagination_config typed as boolean in domain.ts"
else
  fail "Endpoint.has_pagination_config missing from domain.ts"
fi

# Endpoint routes in App.tsx
if grep -q "profileId/endpoints" "$FRONTEND/src/App.tsx" 2>/dev/null; then
  pass "Endpoint routes present in App.tsx"
else
  fail "Endpoint routes missing from App.tsx — check P5.F-01"
fi

# Frontend toolchain checks
(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) \
  && pass "npm run typecheck passes (criteria #17)" \
  || fail "npm run typecheck failed — run: cd frontend && npm run typecheck"

(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) \
  && pass "npm run build passes (criteria #17)" \
  || fail "npm run build failed — run: cd frontend && npm run build"

(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) \
  && pass "npm test passes (criteria #17)" \
  || fail "npm test failed — run: cd frontend && npm test"

(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) \
  && pass "npm run lint passes (criteria #17)" \
  || fail "npm run lint failed — run: cd frontend && npm run lint"

# ── Manual verification reminders ─────────────────────────────────────────────
echo ""
warn "Manual verification needed (browser tests):"
warn "  criteria #18: /profiles/{id}/endpoints renders EndpointListPage"
warn "  criteria #18: 'Endpoints' button on ProfileCard navigates to endpoint list"
warn "  criteria #19: Strategy switcher shows correct field groups per strategy"
warn "  criteria #19: Switching strategy clears strategy_params, preserves max_pages etc."
warn "  criteria #20: Auto-Detect button DISABLED on /endpoints/new form"
warn "  criteria #20: Auto-Detect button ENABLED on /endpoints/{id}/edit form"
warn "  criteria #21: Both GitHub CI workflows pass on push"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 5 COMPLETE — Increment 2 unlocked — proceed to Phase 6${NC}"
  echo ""
  echo -e "  Phase 6 (Schema Inference) can now call:"
  echo -e "  ${BOLD}PaginationEngine().paginate(endpoint, ...)${NC} without ValueError"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 5 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi
