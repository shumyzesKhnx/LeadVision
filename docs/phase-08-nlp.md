# Phase 8: understand the saved website text

The worker now prepares saved text and asks your local Ollama model to describe the company. It saves a short summary, cited products/markets, an optional industry candidate and clearly labelled opportunity hypotheses. It keeps employee count unknown unless explicitly supported, and respects your entered corrections.

Your flow is **agency → services → ICP → campaign → lead → saved evidence → job → business analysis**. Computer vision, semantic matching and scoring come next.

## Quick check in Swagger

The server and worker should be running. Open [Swagger](http://127.0.0.1:8000/docs). Execute `GET /api/v1/health`: schema should be **8**, worker **available**, and **generation_model** available. Your already-installed model is `qwen2.5:3b`.

If you have not tried saved evidence yet, follow the [Phase 7 upload steps](phase-07-saved-evidence.md) using its example files, then submit the job. It will now include the NLP stages.

If you already have a partial Phase 7 job:

1. Execute `GET /api/v1/leads`. Copy your test lead's `latest_job_id`.
2. Open `POST /api/v1/jobs/{job_id}/retry`. Paste that job ID, use a new **Idempotency-Key** such as `phase8-demo-1`, and request body `{}`.
3. Copy the returned `job_id` into `GET /api/v1/jobs/{job_id}`. Execute again after a short wait. **preprocess_text** and **business_analysis** should finish.
4. Copy the returned `run_id` into `GET /api/v1/runs/{run_id}`. Look for **business_analysis → result → summary**. Products/markets may be empty when the model cannot confidently extract them.
5. `summary_sources` and cited fields include exact supporting quotes. Source `website_text` maps to the evidence ID in **provenance → sources**. Use `GET /api/v1/runs/{run_id}/evidence` to inspect that source.

The overall job is still **partial**, with `STAGE_NOT_IMPLEMENTED` at **visual_metrics**. This is expected until Phase 9. A summary is not a lead score or proof that the company needs your service. Model interpretations remain marked for review.

## What happens internally

1. The worker preserves original text offsets, removes repeated lines, and selects a small bounded excerpt.
2. The job saves the model digest, prompt/schema version, parameters, manual inputs and service context it used.
3. Ollama returns structured JSON. The system checks its fields, lengths, source IDs and exact quotes. Unsupported employee counts become unknown.
4. One repair or temporary transport retry is allowed, sharing a maximum of two model calls.
5. Valid results and their stage/activity record commit together. An identical retry can reuse a validated cache. Changed text, corrections, reviews, service context, model or prompt changes the cache input.

Generated results do not overwrite your lead, contact details or pipeline state. Manual industry/employee-count entries take precedence and are labelled as user-provided. An opportunity is a hypothesis supported by observations, not a confirmed purchase need. Exact quote matching does not prove a model's interpretation is correct.

If Ollama is unavailable or returns invalid output, earlier evidence stays available and ordinary agency/lead editing continues. Failed raw responses are bounded private diagnostic files, excluded from public responses and Git, with 24-hour cleanup. Cancelled HTTP requests are closed at the next cancellation check; the local runtime may need time to release its computation.

## Files

| File | Purpose |
|---|---|
| `backend/app/modules/nlp/nlp_service.py` | Select text while preserving source offsets and trim decisions |
| `backend/app/modules/nlp/business_analysis_service.py` | Prompt, validate claims, respect corrections and save results |
| `backend/app/modules/nlp/model_cache_service.py` | Refresh local-model readiness and find exact-input cached results |
| `backend/app/modules/nlp/ollama_client.py` | Bounded local HTTP calls and cancellation |
| `backend/app/modules/nlp/business_analysis_v1.txt` | Versioned instructions that treat website text as data |
| `backend/app/modules/nlp/business_analysis_schema.py` | Strict model-output structure |
| `backend/app/modules/nlp/business_analysis_model.py` | Runtime metadata, immutable results and private diagnostics |
| `backend/app/modules/foundation/008_business_analysis.py` | Add Phase 8 database tables |
| `scripts/benchmark_models.py` | Run a separate local trial with temporary data |
| `backend/tests/unit/test_business_output.py`, `test_ollama_client.py` | Quote/schema/token selection and transport/cancellation checks |
| `backend/tests/integration/test_model_failure.py` | Cache, repair, corrections, model changes and review races |

Use `.\scripts\test.ps1` for offline automated checks. To repeat the real local trial, run:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_models.py
```

The trial creates its own temporary database and leaves your real records unchanged. Its report is `.cache/phase-08/model-trial.json`. The two final trial fixtures passed in approximately **15.5 and 10.7 seconds**. This is a small integration check; broader quality evaluation and peak model RAM measurement remain pending. The installed model uses the **Qwen Research License**, recorded in `docs/model-manifest.json`.

Settings are in `backend/.env.example`: context 4,096 tokens, output 768, selected evidence 1,600 UTF-8 bytes and call timeout 110 seconds. Selection uses a conservative byte-based token bound, rather than an exact tokenizer count, and records actual runtime counts. Start with these small excerpts before increasing limits.

The adapter follows Ollama's official [generation API](https://docs.ollama.com/api/generate) and [structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs).

Verified for this phase: **286 tests passed in 34.30 seconds**, and both real local-model fixtures passed. Earlier model startup took about 28 seconds, so the first request can take longer than subsequent ones. Schema 8 preserved all existing application records and passed foreign-key checks. Swagger returned HTTP 200; health reported the worker and configured model available. No trial leads, uploads or analyses were written into your real database.

## Summary reliability fix, 9 October 2026

The live Arbisoft trial exposed invalid citations: the model joined separate website lines into quotes and used a heading number as an observation ID. Another failure path cut off an answer at its output-token limit before normal repair/diagnostic handling. These were real summary failures; acquisition, image measurements and scoring were retained.

Prompt version `business_analysis_v2` uses `business_analysis_v2.txt`; the original v1 prompt is preserved. Model generation now uses a concise schema: summary <=240 characters, at most two summary citations/products/markets and one opportunity, quote choices drawn only from unchanged selected source excerpts, and controlled observation names. The stored response contract and exact source checks are unchanged. Prompt input omits offsets the model does not need; provenance retains them. Invalid references to absent observations still fail validation. Truncated responses now enter the same bounded repair/diagnostic path. A failed repair cannot introduce a third model call through transport retry. No invalid or partial JSON is accepted as a successful summary.

Actual local-model regression runs for the previously captured Arbisoft text/image, a basic company and an instruction-injection fixture all finished **completed** with validated summaries and unknown employee counts retained as null. The Arbisoft fixture also retained image/semantic results and a score. These were isolated cached/uploaded trials, not fresh live collection or edits to your real leads. Results are in `.cache/nlp-fix/results.json`. Model interpretations still need human review; exact quotes are provenance checks, not proof of every interpretation.

Validation: the complete suite passed **393 tests**, followed by **29 focused checks** after the final repair-budget test and prompt-file change. Historical failed runs are not rewritten. Restart both API and worker; retry the old job with a new idempotency key to produce a new run. No database migration or model download is needed for this fix.
