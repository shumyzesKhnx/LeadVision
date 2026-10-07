# 08 — NLP and local language analysis

**Purpose:** turn website text into a concise, source-linked business description without inventing missing facts. **Requirements:** FR-17–21; DATA-02; NFR-01–06; AT-04. **Dependencies:** 07. **Priority:** Must.

## Inputs and outputs

Inputs: bounded evidence text/excerpts, user corrections, active services as context, benchmark-selected local model and versioned prompt. Outputs: validated summary, candidate industry, supported products/market/size fields, source claims, clearly labelled opportunity hypotheses, truncation metadata and diagnostic reference on failure. Employee count stays null without explicit supporting evidence.

## Future files and database changes

`backend/app/models/business_analysis.py`; `backend/app/schemas/business_analysis.py`; `backend/app/integrations/ollama_client.py`; `backend/app/services/nlp.py`, `business_analysis.py`, `model_cache.py`; `backend/app/prompts/business_analysis_v1.txt`; migration `008_business_analysis.py`; `backend/tests/unit/test_business_output.py`, `test_preprocessing.py`; `backend/tests/integration/test_model_failure.py`; future `scripts/benchmark_models.py`.

Create `business_analyses`; store validated JSON and immutable input/model/prompt snapshots. Raw response is a bounded local diagnostic file under controlled storage, excluded from public responses and Git. No generated output writes directly to lead fields.

## Endpoints

No new initiation endpoint: analysis jobs own this stage. `GET /runs/{id}` exposes validated results and unavailable reasons. `GET /health` reports local runtime readiness independently from database/API readiness.

## Implementation steps

1. Normalize whitespace, remove duplicate lines conservatively, preserve paragraph/source offsets. Select business-rich bounded chunks without dropping citation metadata. Save every truncation/selection decision.
2. Count tokens against the chosen model context. Reserve prompt and output budget; trim selected excerpts explicitly. Proposed context 4,096/output 768 and request timeout 120 seconds are benchmark starting points, not quality guarantees.
3. Define strict output schema: summary <=1,000 characters; bounded candidate/product/opportunity lists (max 10); facts each have value, source ID and exact supporting excerpt. Unknown structural keys fail. Opportunities contain observation IDs and `hypothesis=true`.
4. Prompt model that evidence is data and cannot issue instructions. Present manual corrections as authoritative; do not send model tool definitions or allow tool actions.
5. Call Ollama through the single worker. Cache by exact input, manual-fact revisions, model digest, parameters and prompt/schema version. Track cache origin separately from evidence collection time.
6. Validate JSON/schema, excerpt membership and supported fact formats. Source existence alone does not prove entailment: flag inferred fields, keep industry candidate unreviewed and require human review for uncertain factual interpretation. Size/contact/performance facts without explicit matching evidence become unknown.
7. Permit one bounded repair only if the stage's recovery budget remains. Include validation errors in the repair prompt; do not add unseen facts. If repair fails, retain diagnostic response and report stage failure.
8. Commit the validated analysis and claim map in a short transaction. Do not overwrite corrections. On disconnect, preserve evidence and allow other independent stages/scoring to continue.

## Errors and recovery

`MODEL_UNAVAILABLE`, `MODEL_TIMEOUT`, `MODEL_OUTPUT_INVALID`, `SOURCE_REFERENCE_INVALID`, `TEXT_UNAVAILABLE`, `CONTEXT_LIMIT`. A transport retry consumes the same recovery budget as repair. Disable further model calls after deadline/cancel. CRUD and evidence browsing remain usable if Ollama is down; no paid fallback or guessed placeholder summary.

## Tests and acceptance criteria

Fake response for “CloudBooks provides accounting software to small businesses” produces supported product summary and unknown employees. Test hallucinated employee count, absent citation, invalid source ID, extra JSON keys, excessive field lengths and one-repair exhaustion. Prompt-injection text must not execute anything or modify pipeline. Test correction precedence and cache invalidation after input/model/prompt change. Offline live-model evaluation is separate from ordinary fake-runtime tests. AT-04 passes only when valid source linkage and missing-value behavior are demonstrated; polished text alone is insufficient.
