#!/usr/bin/env bash
# scripts/validate-phase7.sh
# Run from repository root: bash scripts/validate-phase7.sh
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
echo -e "${BOLD}  Phase 7 Validation — Data Preview and Export${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Engine tuple change ───────────────────────────────────────────────────────
echo -e "\n${BOLD}── PaginationEngine Tuple Yield ─────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.pagination.engine import PaginationEngine
import inspect
src = inspect.getsource(PaginationEngine.paginate)
assert 'yield records, body' in src, 'FAIL: still yielding bare lists'
print('OK')
" 2>/dev/null) && pass "PaginationEngine yields (records, body) tuples — criteria #1" \
  || fail "Engine still yields bare lists — apply 'yield records, body' change (P7.A-01)"

# ── Phase 6 regression: _fetch_sample updated ────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.schema_inference.engine import SchemaInferenceEngine
import inspect
src = inspect.getsource(SchemaInferenceEngine._fetch_sample)
assert ('for page_records, _raw_body in' in src or 'for page_records, _ in' in src), \
    'SchemaInferenceEngine._fetch_sample still uses bare for loop — Phase 6 broken'
print('OK')
" 2>/dev/null) && pass "SchemaInferenceEngine._fetch_sample unpacks tuples — Phase 6 intact" \
  || fail "REGRESSION: schema_inference/engine.py _fetch_sample still uses 'for page_records in' — update to unpack tuple"

# ── DataPreviewService importable ─────────────────────────────────────────────
echo -e "\n${BOLD}── DataPreviewService ───────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.data_preview import (
    DataPreviewService, PreviewResult, ColumnMeta, PreviewNoFieldsError
)
print('OK')
" 2>/dev/null) && pass "DataPreviewService, PreviewResult, ColumnMeta importable — criteria #2" \
  || fail "DataPreviewService import failed — check data_preview.py"

# ── has_more detection ────────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.data_preview import DataPreviewService
import inspect
src = inspect.getsource(DataPreviewService.preview)
assert 'row_limit + 1' in src, 'Service must request row_limit+1 records for has_more detection'
assert 'has_more' in src
print('OK')
" 2>/dev/null) && pass "DataPreviewService requests row_limit+1 for has_more detection — criteria #5" \
  || fail "has_more detection broken — service must use 'row_limit + 1' in paginate() call"

# ── raw_response_body truncation ──────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.data_preview import DataPreviewService
import inspect
src = inspect.getsource(DataPreviewService.preview)
assert '50_000' in src or '50000' in src, 'raw_response_body must be truncated at 50000 chars'
print('OK')
" 2>/dev/null) && pass "raw_response_body truncated at 50,000 chars — criteria #6" \
  || fail "raw_response_body truncation missing — add [:50_000] to json.dumps() call"

# ── get_at_path used ──────────────────────────────────────────────────────────
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.services.data_preview import DataPreviewService
import inspect
src = inspect.getsource(DataPreviewService.preview)
assert 'get_at_path' in src, 'Service must use get_at_path for nested field extraction'
print('OK')
" 2>/dev/null) && pass "DataPreviewService uses get_at_path() for nested key_path extraction — criteria #7" \
  || fail "DataPreviewService not using get_at_path — dot-notation key_paths will not traverse nested objects"

# ── Preview URL resolves ──────────────────────────────────────────────────────
echo -e "\n${BOLD}── URL Routing ──────────────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from django.urls import reverse
url = reverse('api_connector:endpoint-preview', kwargs={'profile_pk': 1, 'pk': 1})
assert url == '/api/connector/profiles/1/endpoints/1/preview/', url
print('OK')
" 2>/dev/null) && pass "POST /api/connector/profiles/<pk>/endpoints/<pk>/preview/ resolves — criteria #3" \
  || fail "Preview URL not resolving — check @action url_name='preview' in EndpointViewSet"

# ── PreviewRequestSerializer validation ──────────────────────────────────────
echo -e "\n${BOLD}── Serializer Validation ────────────────────────────${NC}"
(cd "$BACKEND" && $PYTHON manage.py shell -c "
from api_connector.serializers.endpoint import PreviewRequestSerializer
s0 = PreviewRequestSerializer(data={'row_limit': 0})
assert not s0.is_valid(), 'row_limit=0 must be invalid'
s101 = PreviewRequestSerializer(data={'row_limit': 101})
assert not s101.is_valid(), 'row_limit=101 must be invalid'
s_default = PreviewRequestSerializer(data={})
assert s_default.is_valid() and s_default.validated_data['row_limit'] == 25
print('OK')
" 2>/dev/null) && pass "PreviewRequestSerializer: 0→invalid, 101→invalid, empty→25 default — criteria #4" \
  || fail "PreviewRequestSerializer validation incorrect — check min_value=1, max_value=100, default=25"

# ── Security ──────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Security ─────────────────────────────────────────${NC}"
FERNET_COUNT=$(grep -r "from cryptography.fernet import Fernet" \
  "$BACKEND/api_connector" --include="*.py" 2>/dev/null \
  | grep -v "encryption.py" | wc -l | tr -d ' ')
[ "${FERNET_COUNT:-0}" -eq 0 ] \
  && pass "No direct Fernet imports outside encryption.py" \
  || fail "Found $FERNET_COUNT Fernet import(s) outside encryption.py — security violation (ADR-005)"

ROWS_LOGGED=$(grep -r "result\.rows\|preview.*rows" "$BACKEND/api_connector" \
  --include="*.py" 2>/dev/null | grep -i "logger\|log\." | wc -l | tr -d ' ')
[ "${ROWS_LOGGED:-0}" -eq 0 ] \
  && pass "Preview rows never logged (potential PII protection — OWASP A09)" \
  || fail "preview rows appear in a log call — may expose PII from API response"

# XSS protection in RawResponseViewer
grep -q "replace.*&lt;\|replace.*lt;" "$FRONTEND/src/features/data-preview/components/RawResponseViewer.tsx" 2>/dev/null \
  && pass "RawResponseViewer HTML-escapes API response body before syntax highlighting (XSS protection)" \
  || fail "SECURITY: RawResponseViewer missing HTML entity escaping — XSS risk from API response content"

# ── Backend tests ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Backend Tests ────────────────────────────────────${NC}"
(cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) && pass "ruff check passes" || fail "ruff check failed"
(cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) && pass "ruff format passes" || fail "ruff format failed"

if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null); then
  COUNT=$(cd "$BACKEND" && "$PYTEST" --collect-only -q 2>/dev/null \
    | grep -oE "^[0-9]+" | head -1 || echo "0")
  [ "${COUNT:-0}" -ge 270 ] \
    && pass "pytest passes — $COUNT tests (≥270 required)" \
    || fail "pytest passes but only $COUNT tests — need ≥270 (missing test_data_preview.py or test_preview_api.py?)"
else
  fail "pytest failed — run: cd backend && pytest -v"
fi

# ── Frontend files ────────────────────────────────────────────────────────────
echo -e "\n${BOLD}── Frontend Files ───────────────────────────────────${NC}"
REQUIRED_FILES=(
  "src/features/data-preview/pages/DataPreviewPage.tsx"
  "src/features/data-preview/components/CellRenderer.tsx"
  "src/features/data-preview/components/DataPreviewTable.tsx"
  "src/features/data-preview/components/RawResponseViewer.tsx"
  "src/features/data-preview/components/ExportButtons.tsx"
  "src/features/data-preview/components/ColumnHeaderTooltip.tsx"
  "src/features/data-preview/hooks/usePreview.ts"
  "src/features/data-preview/api/previewApi.ts"
  "src/features/data-preview/api/exportUtils.ts"
  "src/features/data-preview/types/preview.ts"
)
ALL_PRESENT=true
for f in "${REQUIRED_FILES[@]}"; do
  if [ ! -f "$FRONTEND/$f" ]; then
    fail "Missing: frontend/$f"
    ALL_PRESENT=false
  fi
done
[ "$ALL_PRESENT" = true ] && pass "All required data-preview frontend files exist"

# useMutation (not useQuery)
grep -q "useMutation" "$FRONTEND/src/features/data-preview/hooks/usePreview.ts" 2>/dev/null \
  && pass "usePreview uses useMutation (not useQuery) — prevents auto-fetch on focus" \
  || fail "usePreview must use useMutation — check hooks/usePreview.ts"

# retry: 0
grep -q "retry: 0" "$FRONTEND/src/features/data-preview/hooks/usePreview.ts" 2>/dev/null \
  && pass "usePreview has retry: 0 (prevents duplicate calls on slow APIs)" \
  || fail "usePreview missing 'retry: 0' — slow APIs may trigger duplicate requests"

# CSV escaping
grep -q "escapeCsvCell" "$FRONTEND/src/features/data-preview/api/exportUtils.ts" 2>/dev/null \
  && pass "exportUtils.ts has CSV cell escaping (prevents comma-in-value corruption)" \
  || fail "CSV cell escaping missing from exportUtils.ts — values with commas will corrupt export"

# Preview route in App.tsx
grep -q "endpointId/preview" "$FRONTEND/src/App.tsx" 2>/dev/null \
  && pass "Preview route present in App.tsx" \
  || fail "Preview route missing from App.tsx — add Route for /profiles/:profileId/endpoints/:endpointId/preview"

# Preview link on EndpointListPage
grep -q "preview" "$FRONTEND/src/features/endpoint/pages/EndpointListPage.tsx" 2>/dev/null \
  && pass "Preview navigation link in EndpointListPage (criteria #11)" \
  || fail "Preview link missing from EndpointListPage — add 'Preview' button to each endpoint row"

# Preview Data link on SchemaExplorerPage
grep -q "preview" "$FRONTEND/src/features/schema-explorer/pages/SchemaExplorerPage.tsx" 2>/dev/null \
  && pass "'Preview Data' link in SchemaExplorerPage (criteria #12)" \
  || fail "'Preview Data' link missing from SchemaExplorerPage"

# Frontend toolchain
(cd "$FRONTEND" && "$NPM" run typecheck > /dev/null 2>&1) && pass "npm run typecheck passes" || fail "npm run typecheck failed"
(cd "$FRONTEND" && "$NPM" run build > /dev/null 2>&1) && pass "npm run build passes" || fail "npm run build failed"
(cd "$FRONTEND" && "$NPM" test > /dev/null 2>&1) && pass "npm test passes" || fail "npm test failed"
(cd "$FRONTEND" && "$NPM" run lint > /dev/null 2>&1) && pass "npm run lint passes" || fail "npm run lint failed"

# ── Manual verification reminders ─────────────────────────────────────────────
echo ""
warn "Manual browser verification needed:"
warn "  #1: POST /preview/ with real API config → 200 with rows, columns, has_more"
warn "  #2: Row limit 25 on paginated API with >25 records → has_more=true"
warn "  #3: No include=True fields → 422; UI shows amber warning with Schema Explorer link"
warn "  #4: datetime field renders formatted (not raw ISO string)"
warn "  #5: null value renders gray 'null' pill (distinct from empty string '')"
warn "  #6: array_of_objects value truncated with 'Expand' button showing full JSON"
warn "  #7: Row limit selector 10→50 triggers new API call; table updates"
warn "  #8: CSV export has alias-named headers; commas in values double-quoted"
warn "  #9: JSON export has alias-named keys in each row object"
warn "  #10: Raw Response toggle shows syntax-highlighted JSON; Copy works"
warn "  #11: 'Preview Data' button on SchemaExplorerPage navigates correctly"
warn "  #12: Both GitHub CI workflows pass on push"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 7 COMPLETE — Increment 3 delivered — proceed to Phase 8${NC}"
  echo ""
  echo -e "  Increment 3 complete: All 6 auth types, all 6 pagination strategies,"
  echo -e "  schema inference and editing, live data preview with CSV/JSON export."
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 7 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi