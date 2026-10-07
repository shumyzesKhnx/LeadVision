# 18 — Local n8n demonstration

**Purpose:** show bounded API coordination while keeping processing logic in Python. **Requirements:** AUTO-01; API-02–04; NFR-01/02/08. **Dependencies:** 06, 11. **Priority:** Should.

## Inputs and outputs

Inputs: manually chosen existing lead ID, loopback API base URL, stable idempotency key for one workflow run. Outputs: credential-free workflow JSON, returned job ID, bounded polling and terminal status summary. n8n does not discover leads, calculate score, generate model text directly or send messages.

## Future files and database changes

`workflows/lead-analysis-manual.json`, `workflows/README.md`; future `docs/evaluation/n8n-demo.md`. **Database changes:** none; jobs identify origin `n8n` without adding duplicate sales activity. **Endpoints:** reuse `POST /leads/{id}/analysis-jobs` and `GET /jobs/{id}`. Saved mode can use prepared approved upload tokens; the initial demonstration may use an already prepared live-test lead.

## Implementation steps

1. Confirm optional local n8n version/license/setup and bind it to loopback. Document its separate memory use; do not require Docker. Install/download remains a future action after core readiness.
2. Build manual trigger -> validate chosen lead -> set API URL/body/key -> HTTP analysis POST. Keep the key constant for retries within one manual execution; create a new execution key for deliberately new analysis.
3. Save returned job ID and poll URL. Wait proposed five seconds between polls, maximum 72 polls (six minutes). Increment attempts on every request; set an overall deadline so network failures cannot extend indefinitely.
4. Stop on completed, partial, failed or cancelled and summarize stage warnings/errors. Queued/running loops continue only within bound. Poll timeout is “workflow stopped waiting,” not proof the backend job failed; show job ID for manual review.
5. Handle POST conflicts: same-key replay follows existing job; ANALYSIS_ACTIVE reports existing ID or stops clearly. Do not create a new key automatically after ambiguous network timeout.
6. Export workflow with no credentials, private lead details, absolute file paths or environment secrets. Document importing, selecting lead, running and inspecting it.

## Errors and recovery

Missing lead/archived campaign/unsafe target/model failure use API errors. HTTP connection failure retries within the same bounded attempt policy. Poll timeout stops the workflow; backend recovery remains module 06's responsibility. n8n failure must not alter scores or pipeline.

## Tests and acceptance criteria

Import clean workflow, trigger a fixture analysis and display completed/partial/failed result. Simulate repeated initiation with same key and verify one job; simulate endless running and verify bounded stop; simulate disconnect and retain job ID. Inspect export for secrets and unsupported nodes. Record screenshot/log of actual run, not a completion claim based on JSON existing. AUTO-01 is separately reported if deferred or instructor-upgraded.
