# Phase 6: jobs and processing workflow

A job is a tracked task for one lead. The API saves the request quickly; a separate worker performs its stages. You can see progress, cancel it, retry it and view its history. Your flow is now **agency → services → ICP → campaign → leads → analysis job**.

## Start and check

Keep two PowerShell terminals open at `E:\LeadVision`:

```powershell
# Terminal 1: API
.\scripts\start.ps1
```

```powershell
# Terminal 2: worker
.\scripts\worker.ps1
```

Open [Swagger](http://127.0.0.1:8000/docs). Execute `GET /api/v1/health`: database should be ready, schema version 6, worker available. An unavailable worker prevents new analysis jobs but does not prevent editing your agency or leads. Stop either process with Ctrl+C. A second worker is blocked by a process lock.

## Try one job

1. Execute `GET /api/v1/leads` and copy Arbisoft's `id`, without quotes.
2. Open `POST /api/v1/leads/{id}/analysis-jobs`, select **Try it out**, and paste that lead ID.
3. Enter `arbisoft-analysis-1` in **Idempotency-Key**. This labels this particular request so repeating it cannot create duplicate work.
4. Use this request body and execute:

```json
{
  "mode": "live",
  "include_supporting_pages": false
}
```

The `202` response contains `job_id`, `run_id` and `poll_url`. Copy `job_id` into `GET /api/v1/jobs/{id}` and execute to see its stages.

**Expected at this phase:** input validation succeeds, then the job reports `failed` with `STAGE_NOT_IMPLEMENTED` at `acquire_text`. This is the correct result because website extraction, NLP, computer vision and scoring are still later modules. Nothing has researched Arbisoft yet. Saved/cached/uploaded modes become usable with phase 7.

## Retry, cancel and history

- Execute the same analysis POST with the same key/body: it returns the original job. A changed body with that key gives an idempotency conflict.
- To retry a failed job, execute `POST /api/v1/jobs/{id}/retry` with its job ID, a **new** key such as `arbisoft-retry-1`, and body `{}`. It creates a new job/run using your current lead and ICP inputs.
- `POST /api/v1/jobs/{id}/cancel` cancels queued work or asks running work to stop at its next checkpoint. Completed stage outputs stay saved. These short phase-6 jobs may finish before you can cancel them manually; automated tests cover cancellation during a longer task.
- `GET /api/v1/leads/{id}/runs` lists attempts. `GET /api/v1/runs/{id}` shows one attempt's saved inputs and job. `is_current` means those inputs still match your current records; it does not mean analysis succeeded.
- Lead responses now show `processing_status` and `latest_job_id`. A lead with active work cannot be deleted until the job stops.

## Files and verification

| Files | Purpose |
|---|---|
| `backend/app/api/jobs.py`, `runs.py` | Submit, poll, cancel, retry and view attempts |
| `backend/app/services/jobs.py`, `workflow.py` | Request rules, saved inputs and stage contracts |
| `backend/app/models/job.py`, `analysis_run.py` | Job, stage and attempt database definitions |
| `backend/app/db/migrations/006_jobs_runs.py` | Adds phase-6 tables without removing earlier data |
| `backend/app/db/repositories/jobs.py` | Reads jobs and history |
| `backend/app/worker/` | Queue, singleton lock, execution and restart recovery |
| `scripts/worker.ps1` | Starts the separate worker |
| `backend/tests/integration/test_job_*.py`, `test_worker_concurrency.py` | Checks duplicates, retries, cancellation, recovery and worker concurrency |

Run `.\scripts\test.ps1` in another terminal. Tests use temporary databases and fake processing handlers; they do not change your real agency, ICP, campaign or leads. They include killing a test worker process and checking recovery, plus confirming API edits still work during a slow task.

The default budget is 300 seconds per job and 120 seconds per stage attempt, with one retry for an explicitly temporary stage failure. Handlers must check cancellation/deadlines and use bounded I/O; arbitrary stuck Python cannot be forcibly stopped by this worker. A running worker retains its lock until it exits. Maintenance prevents new claims. After a stopped worker releases its lock, the next worker marks unfinished running jobs interrupted; you can retry them.

Next: **phase 7 saved text and image evidence**, then NLP, computer vision, semantic matching and scoring.

Verified on 8 October 2026: **234 tests passed in 21.33 seconds**. The real database upgraded to schema 6 with all earlier application records unchanged, including two leads. Swagger returned HTTP 200, all six job/run routes appeared in OpenAPI, and health reported the separate worker available. No demonstration jobs were inserted into your real data during verification.
