#!/usr/bin/env bash
# scripts/validate-phase0.sh
# Run from repository root: bash scripts/validate-phase0.sh
# Exits 0 on full pass, non-zero on any failure.
#
# Fixes applied vs Version 1:
# - Absolute paths for Python/pytest/ruff (relative paths break after cd)
# - manage.py check --verbosity=0 (--quiet is not a valid Django flag)
# - npm test exit code check (grep on output was unreliable)
# - ((PASS++)) || true (prevents pipefail exit when counter is 0)

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

# Capture the repo root so we can build absolute paths
REPO_ROOT="$(pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
VENV="$BACKEND/.venv"

# Build absolute paths to tools — critical when running after cd commands
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

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Phase 0 Validation${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"

# ── Backend Structure (Criterion #22) ────────────────────────────────────────
echo ""
echo -e "${BOLD}── Backend Structure ────────────────────────────────${NC}"
EXPECTED_INITS=(
  "api_connector/__init__.py"
  "api_connector/models/__init__.py"
  "api_connector/services/__init__.py"
  "api_connector/serializers/__init__.py"
  "api_connector/views/__init__.py"
  "api_connector/migrations/__init__.py"
)
ALL_INITS=true
for f in "${EXPECTED_INITS[@]}"; do
  if [ ! -f "$BACKEND/$f" ]; then
    fail "Missing: backend/$f"
    ALL_INITS=false
  fi
done
[ "$ALL_INITS" = true ] && pass "All api_connector __init__.py files present (criterion #22)"

# ── manage.py check (Criterion #7) ───────────────────────────────────────────
# Use --verbosity=0 not --quiet (--quiet is not a valid Django management flag)
if (cd "$BACKEND" && "$PYTHON" manage.py check --verbosity=0 2>/dev/null); then
  pass "python manage.py check passes (criterion #7)"
else
  fail "python manage.py check failed (criterion #7) — run manually to see errors"
fi

# ── showmigrations (Criterion #8) ────────────────────────────────────────────
if (cd "$BACKEND" && "$PYTHON" manage.py showmigrations api_connector 2>/dev/null | grep -q "api_connector"); then
  pass "api_connector app recognized by Django (criterion #8)"
else
  fail "api_connector app not recognized — check INSTALLED_APPS (criterion #8)"
fi

# ── ruff (Criteria #5 + #6) ──────────────────────────────────────────────────
if command -v "$RUFF" &>/dev/null; then
  (cd "$BACKEND" && "$RUFF" check . --quiet 2>/dev/null) && pass "ruff check passes (criterion #5)" || fail "ruff check failed — run: cd backend && ruff check . (criterion #5)"
  (cd "$BACKEND" && "$RUFF" format --check . --quiet 2>/dev/null) && pass "ruff format check passes (criterion #6)" || fail "ruff format check failed — run: cd backend && ruff format . (criterion #6)"
else
  warn "ruff not found at $RUFF — skipping lint checks"
fi

# ── pytest (Criterion #4) ─────────────────────────────────────────────────────
if (cd "$BACKEND" && "$PYTEST" --tb=short -q 2>/dev/null | grep -q "passed"); then
  pass "pytest passes with at least 1 test (criterion #4)"
else
  fail "pytest failed or no tests found — run: cd backend && pytest -v (criterion #4)"
fi

# ── Environment files (Criteria #15 + #16) ───────────────────────────────────
echo ""
echo -e "${BOLD}── Environment Configuration ────────────────────────${NC}"
[ -f "$REPO_ROOT/backend/.env.example" ] && pass "backend/.env.example exists (criterion #15)" || fail "backend/.env.example missing"
[ -f "$REPO_ROOT/frontend/.env.example" ] && pass "frontend/.env.example exists (criterion #16)" || fail "frontend/.env.example missing"

REQUIRED_BACKEND_KEYS=("DJANGO_SECRET_KEY" "DEBUG" "ALLOWED_HOSTS" "DATABASE_URL" "ENCRYPTION_KEY" "CORS_ALLOWED_ORIGINS" "SECURE_SSL_REDIRECT" "OAUTH_REDIRECT_URI")
ALL_KEYS=true
for key in "${REQUIRED_BACKEND_KEYS[@]}"; do
  grep -q "^${key}=" "$REPO_ROOT/backend/.env.example" 2>/dev/null || { fail "backend/.env.example missing key: $key"; ALL_KEYS=false; }
done
[ "$ALL_KEYS" = true ] && pass "All 8 required keys in backend/.env.example (criterion #15)"

grep -q "^VITE_API_BASE_URL=" "$REPO_ROOT/frontend/.env.example" 2>/dev/null \
  && pass "frontend/.env.example has VITE_API_BASE_URL (criterion #16)" \
  || fail "frontend/.env.example missing VITE_API_BASE_URL"

# ── .env gitignored (Criteria #17 + #18) ─────────────────────────────────────
git -C "$REPO_ROOT" check-ignore -q backend/.env 2>/dev/null \
  && pass "backend/.env is gitignored (criterion #17+18)" \
  || fail "backend/.env is NOT gitignored — check .gitignore"
git -C "$REPO_ROOT" check-ignore -q frontend/.env 2>/dev/null \
  && pass "frontend/.env is gitignored (criterion #17)" \
  || fail "frontend/.env is NOT gitignored — check .gitignore"

# ── .env.example NOT gitignored ──────────────────────────────────────────────
git -C "$REPO_ROOT" check-ignore -q backend/.env.example 2>/dev/null \
  && fail "backend/.env.example is being gitignored — it must be committed" \
  || pass "backend/.env.example is tracked (not ignored)"

# ── Frontend structure (Criterion #23) ───────────────────────────────────────
echo ""
echo -e "${BOLD}── Frontend Structure ───────────────────────────────${NC}"
BARREL_COUNT=$(find "$FRONTEND/src/features" -name "index.ts" 2>/dev/null | wc -l | tr -d ' ')
if [ "${BARREL_COUNT}" -ge 24 ]; then
  pass "Feature barrel files: $BARREL_COUNT found, expected 24 (criterion #23)"
else
  fail "Expected 24 feature barrel files, found $BARREL_COUNT (criterion #23)"
fi

# shadcn components in correct location (not a literal @/ directory)
if [ -f "$FRONTEND/src/shared/components/ui/button.tsx" ]; then
  pass "shadcn components at correct path: src/shared/components/ui/"
else
  fail "shadcn button.tsx not found at src/shared/components/ui/ — check for literal @/ directory"
fi

# Single tsconfig.json (no project references)
if [ -f "$FRONTEND/tsconfig.json" ] && [ ! -f "$FRONTEND/tsconfig.app.json" ]; then
  pass "Single flat tsconfig.json (no project references) — criterion #24"
else
  warn "tsconfig.app.json exists — project references in use (may cause composite conflicts)"
fi

# ── Frontend checks (Criteria #11 + #12 + #13 + #14) ─────────────────────────
(cd "$FRONTEND" && npm run typecheck --silent 2>/dev/null) \
  && pass "npm run typecheck passes (criterion #14)" \
  || fail "npm run typecheck failed — run: cd frontend && npm run typecheck (criterion #14)"

(cd "$FRONTEND" && npm run build --silent 2>/dev/null) \
  && pass "npm run build passes (criterion #11)" \
  || fail "npm run build failed — run: cd frontend && npm run build (criterion #11)"

(cd "$FRONTEND" && npm run lint --silent 2>/dev/null) \
  && pass "npm run lint passes (criterion #13)" \
  || fail "npm run lint failed — run: cd frontend && npm run lint (criterion #13)"

# Direct exit code check — more reliable than grepping output across vitest versions
if (cd "$FRONTEND" && npm test 2>/dev/null); then
  pass "npm test passes (criterion #12)"
else
  fail "npm test failed — run: cd frontend && npm test (criterion #12)"
fi

# ── CI workflow files (Criteria #19 + #20) ───────────────────────────────────
echo ""
echo -e "${BOLD}── CI Workflows ─────────────────────────────────────${NC}"
[ -f "$REPO_ROOT/.github/workflows/backend-ci.yml" ] \
  && pass "backend-ci.yml exists (criterion #19)" \
  || fail "backend-ci.yml missing (criterion #19)"
[ -f "$REPO_ROOT/.github/workflows/frontend-ci.yml" ] \
  && pass "frontend-ci.yml exists (criterion #20)" \
  || fail "frontend-ci.yml missing (criterion #20)"
[ -f "$REPO_ROOT/.nvmrc" ] \
  && pass ".nvmrc exists: $(cat "$REPO_ROOT/.nvmrc")" \
  || fail ".nvmrc missing — Node version not pinned"

warn "Manual verification needed: criteria #1-3 (running servers), #9 (dbshell), #10 (browser), #21 (GitHub Actions pass)"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}  ${YELLOW}${WARN} warnings${NC}"
echo -e "${BOLD}════════════════════════════════════════════════════${NC}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✓ Phase 0 COMPLETE — ready to start Phase 1${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}✗ Phase 0 INCOMPLETE — fix the ${FAIL} failure(s) above${NC}"
  exit 1
fi
