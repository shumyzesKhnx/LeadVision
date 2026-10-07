# Technical decisions

## Module 02 — Agency and services

Implemented singleton profile and service CRUD/deactivation with schema version 2. Contact fields are email, phone and HTTP/HTTPS website; PATCH replaces the contact object. Service lists default to active records, with include_inactive and pagination. GET by service ID is added to expose the current ETag conveniently. Mutations use short IMMEDIATE transactions and revision-checked updates; identical edits retain their revision. Activities record changed field names/revisions rather than full descriptions or contact details. Migration 002 rebuilds both activities and their dependent cleanup table transactionally to preserve existing links while adding the agency FK. Future draft freshness compares captured service revisions; no draft tables are assumed before module 13.

## Folder organization

Backend code, tests, dependencies and local configuration live in `backend/`. The future browser interface lives in `frontend/`; helper commands live in `scripts/`; plans and verification remain in `docs/`. Runtime data stays in root `data/`, and the existing root `.venv/` is reused. All implementation-plan paths follow this layout.

## Phase 1 — 7 October 2026

- **Implemented:** FastAPI API shell, SQLAlchemy/SQLite, explicit short transactions, WAL and per-connection foreign keys, numbered migration ledger, safe errors and storage helpers. The API acquires/releases database resources through [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).
- **Tested environment:** Windows 11, Python 3.14.8, approximately 247 GB free on E: when measured. These are foundation observations, not model performance measurements.
- **Dependencies:** exact versions are in `backend/requirements.lock.txt`. FastAPI is constrained below 0.130 for the tested Starlette/HTTPX TestClient stack. The first resolution selected FastAPI 0.142.2/Starlette 1.7.0, whose TestClient deprecates HTTPX; the tested selection is FastAPI 0.129.2/Starlette 0.52.1. Only Starlette's known AnyIO BlockingPortal alias deprecation is filtered in pytest; other warnings remain errors.
- **Database:** foreign keys are enabled for every connection, and BEGIN is explicit so failed DDL rolls back. See [SQLAlchemy's SQLite documentation](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html). Migration 001 contains frozen DDL, so future ORM changes do not silently change old migrations.
- **Configuration:** Pydantic Settings loads `backend/.env` and environment variables; invalid inputs are hidden in validation error text. See [Pydantic Settings documentation](https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/).
- **Scope:** worker state, maintenance flag and cleanup helpers exist; there is no job worker, business CRUD, coordinated backup/restore or AI processing yet. Activity domain foreign keys arrive when agency/campaign/lead tables exist.
- **Deferred compatibility:** use installed Python for phase 1; check Torch/OpenCV/Playwright and model memory in their own modules. No model or optional package was downloaded.
- **Swagger:** default CDN assets are retained for this backend shell. Health/tests work offline after dependencies are installed; the saved-evidence offline UI remains required later.
- **Git:** executable unavailable in the terminal. Local initialization and first push have not occurred; install/configure Git before starting source history.
