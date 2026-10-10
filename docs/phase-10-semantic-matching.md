# Phase 10: compare company meaning with your ICP

Your system can now ask: **How similar is this company's description to the type of customer I want?**

It uses a local MiniLM embedding model to turn both texts into comparable number lists, then compares them. You see the raw cosine and a similarity value from 0 to 100. This is one part of the future lead score. It is not a percentage chance that the company will become a customer.

## Quick Swagger check

1. Open [Swagger](http://127.0.0.1:8000/docs). Execute `GET /api/v1/health`: schema should be **10**, worker **available**, and **embedding_model** available.
2. Use a lead with a saved-evidence job. Its campaign's ICP must have meaningful `target_text`. A blank target produces unavailable similarity.
3. Execute `POST /api/v1/jobs/{job_id}/retry` with that job ID, body `{}`, and a new **Idempotency-Key**, such as `phase10-demo-1`. For a first saved upload, follow the [Phase 7 steps](phase-07-saved-evidence.md).
4. Poll `GET /api/v1/jobs/{job_id}` using the returned job ID. The **semantic_match** stage should finish.
5. Execute `GET /api/v1/runs/{run_id}` using the returned run ID. In **Response body**, find **semantic_result → result → normalized_similarity**.
6. **provenance** shows which company text was used, the ICP version, model revision, selected text, truncation and cache reuse.

The job stays **partial** because the **score** stage is Phase 11. Missing text or an unavailable embedding model produces null similarity and a reason, while other saved results remain available. Ordinary agency/lead editing continues.

## Which text is compared?

The order is: your entered lead description, otherwise a validated generated summary, otherwise saved website text. User-entered text is labelled as user-provided. Generated interpretations remain review-required. Rejected saved text cannot supply the comparison; an independently entered description can still be used.

Changing the description recomputes its vector. Changing ICP target text, desired needs or free-text preferences recomputes the target vector. The target combines those three fields, matching the saved semantic-input hash; free-text preferences remain soft context. Editing industry or location makes the earlier run stale for scoring, while unchanged description vectors can still be reused. Source review changes also affect currentness. Deleting a lead removes its unshared company vectors and keeps vectors still used by another lead; ICP vectors remain separate.

The same model revision and configuration must be used on both sides. Zero, nonfinite or incompatible vectors produce missing similarity. The formula is **100 × max(0, cosine)**, with numerical clipping to the valid range. A zero similarity is different from missing evidence.

## Local model and files

MiniLM produces 384-dimensional vectors. We use its pinned ONNX export with CPU inference, attention-mask mean pooling and L2 normalization. Selection explicitly caps input at 256 tokens including special tokens, with a 12,000-character preprocessing bound; every trim is recorded. These settings follow the [official model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). The model is primarily intended for English; other-language quality remains unevaluated.

Model files are under the ignored `models/all-minilm-l6-v2/` folder. The worker verifies downloaded artifacts and performs inference locally. It does not download models during a job. On another computer, install dependencies and run:

```powershell
.\.venv\Scripts\python.exe scripts/setup_embeddings.py
.\scripts\start.ps1
.\scripts\worker.ps1
```

Keep the server and worker in separate terminals. Local settings can override `LEADVISION_EMBEDDING_MODEL_DIR`. API submission uses worker-refreshed model metadata and does not load the encoder or perform inference.

| File | Purpose |
|---|---|
| `backend/app/modules/semantics/embedding_config.py` | Pin artifact revision, checksums and compatible settings |
| `backend/app/modules/semantics/embedding_model_client.py` | Verify local files, select tokens and run CPU inference |
| `backend/app/modules/semantics/embeddings_service.py` | Validate, cache, compare and rank vectors |
| `backend/app/modules/semantics/semantic_matching_service.py` | Choose company text, compare it with the ICP and save provenance |
| `backend/app/modules/semantics/embedding_model.py`, `semantic_result.py` | Runtime readiness, owned vector cache, lead references and immutable results |
| `backend/app/modules/foundation/010_embeddings_semantics.py` | Add four Phase 10 tables |
| `scripts/setup_embeddings.py` | Explicit checksum-verified download from the pinned official repository |
| `scripts/benchmark_embeddings.py` | Real local model trial without changing your application database |
| `backend/tests/unit/test_cosine.py`, `test_embedding_selection.py` | Maths, invalid vectors, ranking and explicit token limits |
| `backend/tests/integration/test_embedding_cache.py` | Cache, source changes, currentness, rejected evidence and safe deletion |

Run `.\scripts\test.ps1` for offline checks. The real model trial runs with `.\.venv\Scripts\python.exe scripts/benchmark_embeddings.py`; its report is `.cache/phase-10/embedding-trial.json`.

## How far to the next features?

| Next step | What it adds |
|---|---|
| **Phase 11: next** | Explained final lead score using industry, location, size and semantic similarity; exclusions and missing-data coverage |
| **Finish Phase 7 live mode: after 11** | Fetch website text and capture screenshots automatically for the companies you add |
| **Phases 12–14** | Agency knowledge, reviewed outreach drafts and pipeline/analytics |
| **Phase 15** | A simple browser interface |
| **Phase 19** | Complete core verification and delivery; optional demonstrations follow |

Requirement scope: SEM-01–SEM-05, FR-05/FR-20, DATA-02 and AT-06 matching work. Broader system performance, multilingual quality and final end-to-end acceptance remain later evaluation work.

Verified on 9 October 2026: **327 tests passed in 53.20 seconds**, including final cache, target-needs/preferences and deletion checks. Schema 10 preserved every existing record in the 21 previous application tables and passed foreign-key checks. Swagger returned HTTP 200; server, worker and both local models were available. A real temporary worker run produced similarity and reused both vectors on retry, without adding trial data to your real database.

The curated accounting description measured **75.48** against the accounting ICP; unrelated construction measured **11.13**. Repeated vectors differed by 0 within the 1e-5 tolerance. Encoder loading took approximately 0.73 seconds, short-text inference around 0.01 seconds, and the full 256-token fixture around 0.15 seconds. Peak benchmark-process working set was approximately 241 MiB, including Python and libraries. These are small local integration measurements, not population accuracy or whole-project benchmarks.
