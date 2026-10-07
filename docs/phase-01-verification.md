# Phase 1 verification

Verified on 7 October 2026, Asia/Karachi. Scope: **module 01, foundation and persistence**. This does not claim that business modules or full SRS acceptance tests are complete.

## Implemented

- FastAPI API shell, health response, Swagger and OpenAPI.
- Configuration in `backend/.env`, loopback-only defaults, and project-root runtime data.
- SQLAlchemy/SQLite, WAL, bounded busy timeout and foreign keys on every connection.
- Migration 001: schema ledger, activities, worker/maintenance state and file-cleanup outbox.
- Migration order/checksums, transactional DDL rollback and refusal of newer/unrecognized schemas. Equivalent Git LF/CRLF line endings do not invalidate checksums.
- UTC timestamps, Asia/Karachi conversion and stable input/content hashes.
- Safe error envelopes/request IDs, field validation, Host/Origin guards and redacted logs.
- Opaque bounded artifact writes, atomic publication, traversal/device/junction rejection.
- Transaction-owned activity recording, retry deduplication, maintenance write guard and retryable cleanup helpers.
- Pinned tested dependencies, `backend/.env.example`, `.gitignore`, candidate-only model manifest and beginner run instructions.

## Actual checks

| Check | Observed result |
|---|---|
| `scripts/test.ps1` | **62 passed in 1.01 seconds**, no skipped tests |
| Migration command repeated after server startup | Schema version 1 retained; no duplicate migration |
| Actual Uvicorn startup on temporary port 8010 | Startup successful; SQLite initialized |
| `GET /api/v1/health` over real local HTTP | 200, status ok, database ready, schema 1 |
| `GET /docs` and `/openapi.json` over real local HTTP | Both 200 |
| Existing Ollama runtime probe | Available; no inference/model download performed |
| Missing/invalid/timeout runtime responses in offline tests | Unavailable without breaking health |
| Restart persistence, failed transaction, failed DDL, newer/changed migrations | Passed |
| FK violations, independent connections, lock timeout | Passed |
| Windows linked-directory/junction escape and staged-write failure cleanup | Passed |
| Host/Origin/preflight/maintenance and safe errors | Passed |

After folder reorganization, use `scripts/start.ps1` from the project root or run `..\.venv\Scripts\python.exe -m app` from `backend/`. Tests use temporary databases/files, not the runtime database.

Reorganization check: all 62 tests passed in 0.99 seconds; the restarted server returned 200 for Swagger and status ok/schema 1 for health. The original `data/leadvision.sqlite3` retains one migration row, no database was created under `backend/data/`, and documentation links resolve. Backend configuration and implementation-plan paths now follow the named folders.

## Environment and limits

Windows 11, Python 3.14.8, about 247 GB free on E: at setup. Exact packages are recorded in `backend/requirements.lock.txt`. These observations do not establish later AI-package compatibility, reference-demo memory/disk use or analysis performance.

Git was unavailable in the terminal; no repository was initialized or pushed. Swagger uses CDN assets and currently needs internet to render; the JSON API and tests work offline once dependencies exist. The worker is correctly reported as not_implemented. The maintenance flag is groundwork for future coordinated backup, not a complete backup/restore implementation.

DATA-01, API-01/04 and NFR-07/08 have foundation evidence. Domain persistence AT-01, real jobs AT-11 and full offline/restore AT-12 still depend on later modules. Next: **02 — agency and services**.
