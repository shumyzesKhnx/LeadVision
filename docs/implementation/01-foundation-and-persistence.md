# 01 — Foundation and persistence

**Purpose:** give every later module the same configuration, durable storage, errors and safe file handling.

**Requirements:** DATA-01–03; API-01, API-04; NFR-01–02, NFR-04, NFR-07–08; SRS pages 16–19 security, technology and repository constraints. **Dependencies:** shared design only. **Priority:** Must.

## Inputs and outputs

Inputs: configured data root, loopback addresses, database URL, environment values, dependency/model candidates. Outputs: importable API shell, migration/session infrastructure, shared validation/error conventions, health response, future setup and model manifests. Health must describe unavailable models without making CRUD unavailable.

## Future files and database changes

- `backend/app/main.py`; `backend/app/core/config.py`, `errors.py`, `clock.py`, `hashing.py`, `storage.py`, `request_guards.py`.
- `backend/app/db/base.py`, `session.py`, `migration_runner.py`; `backend/app/db/migrations/001_foundation.py`.
- `backend/app/models/activity.py`, `maintenance.py`; `backend/app/services/activity.py`; `backend/app/api/health.py`; `backend/app/schemas/common.py`.
- `backend/.env.example`, `.gitignore`, dependency input/lock files, `README.md`, `docs/model-manifest.json`, `docs/decisions.md`.
- Tests: `backend/tests/unit/test_storage.py`, `test_errors.py`; `backend/tests/integration/test_database.py`, `test_request_guards.py`.

Create `schema_versions`, `activities`, `worker_state`, `file_cleanup_tasks`. Activities may gain domain FKs through later migrations. Turn on foreign keys for all connections; add WAL and bounded lock waiting. UTC timestamps are shared helpers, not ad hoc local times.

## Endpoints

`GET /api/v1/health` returns dependency readiness and application/schema version. `/docs` exposes FastAPI contracts. No route may return arbitrary filesystem data. Apply the shared error handler to validation errors as well as service exceptions.

## Implementation steps

1. Confirm Windows version, free disk space and a compatible Python/dependency combination. Record model candidates and licences now; run generation/embedding benchmarks when implementing 08/10, and optional CNN in 16. Do not block basic CRUD on all model downloads. Do not equate Python currently available with proven compatibility.
2. Create the minimal responsibilities and configuration defaults from the shared design. Fail clearly on invalid startup configuration. Keep example secrets blank and actual `.env` out of Git.
3. Add database sessions, migration checksums, foreign keys and rollback behavior. Run a migration twice to verify repeatability; reject a DB newer than supported schema.
4. Add bounded error serialization, request IDs and diagnostic logs. Protect Host/Origin, restrict CORS and bind to loopback.
5. Add storage functions that generate opaque artifact keys, resolve beneath the configured root, reject path traversal/reparse-point escape, stage writes and atomically rename validated files.
6. Add append-only activity recording with unique event keys. Define deletion outbox helpers and maintenance mode so later backup work can pause writes safely.
7. Write setup instructions and exclusion rules for models, environments, DB/WAL files, private leads, credentials and large artifacts. Git and GitHub actions remain future delivery work.

## Errors and recovery

Invalid paths/config fail startup with a local diagnostic. DB unavailable produces a safe `503 DATABASE_UNAVAILABLE`; unexpected errors give `500 INTERNAL_ERROR` with request ID only. Lock exhaustion yields retryable `503 DATABASE_BUSY`. Never create a fresh empty database silently when restore/setup expected an existing one. Storage failure removes incomplete staged writes and records cleanup when required.

## Tests and acceptance criteria

- Foreign-key violation fails on API and worker connections; failed transaction leaves prior committed data intact.
- Restart preserves a fixture row; repeated migration does not duplicate schema/data.
- Traversal, absolute path, symlink/reparse escape and hostile Origin are rejected. Response contains no private path or traceback.
- UTC round-trip and Asia/Karachi display conversion are deterministic. Secret-like configuration is redacted.
- Basic API/Swagger starts with Ollama stopped. Configuration and pinned dependency instructions reproduce the shell on a fresh local environment.

Acceptance evidence starts AT-01, AT-11 and AT-12. Hardware values remain targets until measured in module 19.
