# ADR-002: api_connector as Local Django App vs. Pip-Installable Package

## Status
Accepted

## Context
The `api_connector` module could be packaged for pip or registered as a local app.

## Options Considered
**Option 1 — Local app:** registered as `'api_connector'` in INSTALLED_APPS; no
packaging overhead; all imports use `from api_connector.models import ...`.

**Option 2 — Pip package:** requires `pyproject.toml` with package metadata, build
tooling, and `pip install -e backend/` in dev setup.

## Decision
Local Django app.

## Rationale
MVP scope is a single host project. Extraction to a package later requires only
adding packaging config — no code changes.

## Consequences
Locks in INSTALLED_APPS entry as `'api_connector'`. Migration files are registered
under the `api_connector` app label.
