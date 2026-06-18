# API Connector

A monorepo: Django/DRF backend (`backend/`) and Vite/React/TypeScript frontend (`frontend/`).

---

## Prerequisites

| Tool       | Minimum Version | Notes                                    |
| ---------- | --------------- | ---------------------------------------- |
| Python     | 3.11+           |                                          |
| Node.js    | 22 LTS          | Use nvm:`nvm install 22 && nvm use 22` |
| PostgreSQL | 15+             | macOS:`brew install postgresql@15`     |

> **macOS:** `psycopg2-binary` requires PostgreSQL client libraries.
> Run `brew install postgresql` even if you use a hosted database.

---

## Local Setup

Follow these steps **in sequence** from a clean clone.

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Configure the backend environment

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in:

**`DJANGO_SECRET_KEY`:**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**`DATABASE_URL`** format: `postgres://USER:PASSWORD@localhost:5432/api_connector_dev`

**`ENCRYPTION_KEY`:**

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> ⚠️ **ENCRYPTION_KEY warning:** Rotating this key invalidates **all** stored
> encrypted credentials. Never rotate without the key rotation procedure
> in `docs/operations.md` (Phase 8).

### 3. Configure the frontend environment

```bash
cp frontend/.env.example frontend/.env
# Default VITE_API_BASE_URL=http://localhost:8000 is correct locally.
```

### 4. Create the PostgreSQL database

**Linux:**

```bash
sudo -u postgres psql -c "CREATE USER \"api_connector_user\" WITH PASSWORD 'localpassword';"
sudo -u postgres psql -c "CREATE DATABASE api_connector_dev OWNER \"api_connector_user\";"
sudo -u postgres psql -d api_connector_dev -c "GRANT USAGE ON SCHEMA public TO \"api_connector_user\"; GRANT CREATE ON SCHEMA public TO \"api_connector_user\";"
```

**macOS (Homebrew PostgreSQL):**

```bash
createuser -s api_connector_user
createdb api_connector_dev -O api_connector_user
psql api_connector_dev -c "ALTER USER api_connector_user WITH PASSWORD 'localpassword';"
```

Update `DATABASE_URL` in `backend/.env`:

```
DATABASE_URL=postgres://api_connector_user:localpassword@localhost:5432/api_connector_dev
```

### 5. Install backend dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 6. Run database migrations

```bash
python manage.py migrate
```

### 7. Start the backend server

```bash
python manage.py runserver
# → http://localhost:8000
```

```bash
curl http://localhost:8000/api/health/
# → {"status":"ok"}
```

### 8. Install frontend dependencies (new terminal)

```bash
cd frontend
npm install
```

### 9. Start the frontend dev server

```bash
npm run dev
# → http://localhost:5173
```

---

## Running Tests

```bash
cd backend && pytest
cd frontend && npm test
```

## Linting and Type Checking

```bash
cd backend && ruff check . && ruff format --check .
cd frontend && npm run lint && npm run typecheck
```

---

## CI

GitHub Actions runs separate **Backend CI** and **Frontend CI** workflows on every push and PR.
Both must pass before merging into `main`.

> **Branch protection is a manual step.** After both workflows run once, configure:
> Settings → Branches → Add rule → require `Backend CI / lint-and-test` and
> `Frontend CI / lint-and-test`. Not automated by workflow files.

---

## Architecture

Monorepo with `backend/` (Django + DRF) and `frontend/` (Vite + React 18).
Both servers run simultaneously in development. PostgreSQL is the **only** supported
database — SQLite is explicitly unsupported. The `api_connector` Django app is the entire
backend; `config/` holds project-level configuration only.

---

## Environment Variables Reference

| File              | Variable                 | Description                                     |
| ----------------- | ------------------------ | ----------------------------------------------- |
| `backend/.env`  | `DJANGO_SECRET_KEY`    | Django cryptographic key. Required. No default. |
| `backend/.env`  | `DATABASE_URL`         | PostgreSQL connection URL.                      |
| `backend/.env`  | `ENCRYPTION_KEY`       | Fernet key for credential encryption at rest.   |
| `backend/.env`  | `CORS_ALLOWED_ORIGINS` | Allowed CORS origins (comma-separated).         |
| `frontend/.env` | `VITE_API_BASE_URL`    | Backend API base URL (no trailing slash).       |

Full annotated reference: `backend/.env.example` and `frontend/.env.example`.
READMEEOF
