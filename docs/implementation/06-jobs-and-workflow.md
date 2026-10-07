# 06 — Persistent jobs and workflow

**Purpose:** run slow analysis without blocking CRUD and recover honestly after interruption. **Requirements:** API-01–04; DATA-01/02; FR-21; NFR-02/03/06; PIPE-02; UC-01/04. **Dependencies:** 05. **Priority:** Must.

## Inputs and outputs

Inputs: lead ID, live/cached/uploaded mode, optional saved-upload token, page-selection flag, idempotency key, current input/config versions. Outputs: immediate job receipt, persistent stage history, immutable analysis run, pollable partial outputs, cancellation/retry records. Generation/index jobs reuse this infrastructure in modules 12–13.

## Future files and database changes

`backend/app/models/job.py`, `analysis_run.py`; `backend/app/schemas/job.py`, `analysis_run.py`; `backend/app/db/repositories/jobs.py`; `backend/app/services/jobs.py`, `workflow.py`; `backend/app/worker/main.py`, `queue.py`, `handlers.py`, `recovery.py`; `backend/app/api/jobs.py`, `runs.py`; migration `006_jobs_runs.py`; `backend/tests/integration/test_job_idempotency.py`, `test_job_recovery.py`, `test_worker_concurrency.py`.

Create `jobs`, `job_stages`, `analysis_runs`, active-lead partial unique indexes and idempotency uniqueness. Use worker_state plus singleton process lock. Lead deletion cancels/blocks active jobs first. No Redis, Celery or model execution in FastAPI BackgroundTasks is needed.

## Endpoints

`POST /leads/{id}/analysis-jobs`; `GET /jobs/{id}`; `POST /jobs/{id}/cancel`; `POST /jobs/{id}/retry`; `GET /leads/{id}/runs`; `GET /runs/{id}`. Require idempotency headers on initiation/retry. Poll responds with stage counts, warnings, bounded error, timestamps and result references. Target initiation time is under two seconds excluding upload transfer.

## Implementation steps

1. Preflight entity existence, active campaign/ICP and selected mode/token. Save canonical request hash, lead/config/model snapshots and run ID transactionally with the job.
2. Implement key reuse and payload-conflict semantics under DB constraints, including simultaneous POSTs. One lead cannot have competing active analysis runs. Duplicate retries are deduplicated by their own key.
3. Implement a separate worker command with a process-lifetime singleton lock. Claim the oldest queued eligible job atomically; release DB transaction before any network/model work. Bound poll interval and update heartbeat between stages.
4. Define stage interfaces now: input snapshot -> validated stage result, warnings, errors, artifact references. Implement modules 07–11 through those interfaces. For this module's tests, fake handlers are explicitly test-only; production missing handlers must fail `STAGE_NOT_IMPLEMENTED`.
5. Commit each stage's result and activity atomically. Use stable event keys such as job/stage/action so an automatic retry does not duplicate sales activity. Do not create automatic qualification/contact activity.
6. Enforce deadline, per-stage retry budget and cancellation. Finish using the shared completed/partial/failed definitions; retain previously committed results.
7. On startup, after acquiring exclusive worker ownership, fail previous running jobs with `JOB_INTERRUPTED`. Revalidate queued snapshots before resuming. Analysis retry creates a new run with current lead/ICP inputs and retry_of history; saved mode reattaches retained validated evidence/manifest without consuming an expired one-time token again. If unavailable, require a fresh upload_token. Index retry targets the current document version; outreach retry revalidates active service/current context and creates a new draft series on success. All retries need a new idempotency key and can reuse only validated caches.
8. At finalize compare current revisions to captured ones and label stale outputs. Integrate model/index/draft handlers later without weakening serialization.

## Errors and recovery

`409 IDEMPOTENCY_CONFLICT`, `ANALYSIS_ACTIVE`, `INPUT_CHANGED`; `503 WORKER_UNAVAILABLE`; `422 SAVED_EVIDENCE_REQUIRED`. Worker stage exceptions are isolated and logged with request/job correlation. Timeout, model disconnect and invalid output become bounded poll errors with stage/retryability; CRUD remains healthy. Reject a second live worker rather than stealing its job.

## Tests and acceptance criteria

Concurrent same-key requests return one job; different body under same key conflicts. Different keys for one active lead do not create competing runs. Kill worker during inference, restart, verify old run failed/interrupted and new retry has a different run ID. Queued changed inputs fail rather than run old data silently. Cancel after text stage retains text. Inject downstream failure and verify partial state. Duplicate stage persistence creates one activity. Run CRUD while fake slow processing runs and verify no long write transaction. AT-11 covers these behaviors; measured timings belong to module 19.
