# 10 — Embeddings and semantic matching

**Purpose:** compare company text with ICP text and provide the same vector machinery for retrieval. **Requirements:** SEM-01–05; FR-05/20; DATA-02; NFR-01–05; AT-06. **Dependencies:** 08 and 03. **Priority:** Must.

## Inputs and outputs

Inputs: selected company description with provenance, ICP target text/version, model revision, tokenizer/preprocessing config. Outputs: cached normalized vectors, raw cosine, separately normalized 0–100 value, source text hashes and availability/currentness. Similarity is not probability of fit or conversion.

## Future files and database changes

`backend/app/modules/semantics/embedding_model.py`, `semantic_result.py`; `backend/app/modules/semantics/semantic_result_schema.py`; `backend/app/modules/semantics/embedding_model_client.py`; `backend/app/modules/semantics/embeddings_service.py`, `semantic_matching.py`; `backend/app/modules/semantics/embeddings_repository.py`; migration `010_embeddings_semantics.py`; `backend/tests/unit/test_cosine.py`; `backend/tests/integration/test_embedding_cache.py`, `test_semantic_freshness.py`.

Create `embeddings`, `semantic_results` with model/config/hash uniqueness and vector references. Encode vectors as bounded float32 BLOB with dimension metadata; never deserialize pickle from uploads. Store one model space per comparison; reject mixing revisions even if dimensions happen to match.

## Endpoints

No separate arbitrary model API. Results are in `GET /runs/{id}` and later score detail. Knowledge retrieval reuses this service in module 12. Model switches are recorded design/config changes that invalidate affected comparisons and indexes.

## Implementation steps

1. Select text in documented precedence: explicit reviewer description, else supported generated summary, else bounded extracted text. Save source choice, input hash and truncation. Empty text produces missing similarity.
2. Load benchmark-selected embedding model locally in CPU mode, pin revision, normalize output and validate finite elements and expected dimension (384 for the candidate).
3. Respect model tokenizer limit for company descriptions, ICP text and knowledge chunks. Record selection/truncation; do not rely on silent tokenizer truncation. A shorter faithful description is preferable to arbitrary full-page text.
4. Cache vectors by agency, purpose, input hash, model revision and config. Company and ICP encoders must share the same compatible settings.
5. Compute cosine = dot(a,b)/(norm(a)*norm(b)). Nonfinite/zero norm means missing. Clip floating-point raw result to [-1,1] only for numerical safety; normalized value = 100*clip(raw,0,1).
6. Persist raw and normalized values, vectors/input hashes and freshness links. Apply hard criteria independently in module 11; similarity never overrides an exclusion.
7. Offer shared bounded NumPy similarity ranking for knowledge chunks. Filter ownership/current version before vector comparison; no vector database required.

## Errors and recovery

`EMBEDDING_UNAVAILABLE`, `EMPTY_TEXT`, `ZERO_VECTOR`, `VECTOR_DIMENSION_MISMATCH`, `MODEL_SPACE_MISMATCH`, `NONFINITE_VECTOR`. These make semantic component missing, not zero. Retry once only for transient runtime failures; no retry for invalid vector/config. Retain validated business/CV outputs and continue scoring available fields.

## Tests and acceptance criteria

Unit vectors verify cosine 1, 0 and -1 plus normalized values 100, 0, 0. Zero/empty vectors give missing. Stable inputs reuse cache; target text/model/config changes invalidate it. Industry/region edits invalidate structured score without unnecessarily recomputing unchanged description vectors. Compare curated accounting-SaaS and unrelated construction descriptions, report observed ordering and investigate unexpected results rather than hardcoding similarity expectations. Repeated pinned-model evaluation stays within documented float tolerance (proposed 1e-5). AT-06 requires comparable model spaces and correct freshness, not a population accuracy claim.

## Implemented milestone

Phase 10 uses the official pinned MiniLM ONNX export with ONNX Runtime CPU and its native tokenizer; it avoids a Torch dependency for this encoder. Local settings, explicit verified setup, cached runtime metadata and run responses are implemented. Token selection records the 256-token cap and a 12,000-character prefix bound. Migration 010 adds vector/runtime/results tables plus lead references for safe shared-cache deletion. See [the walkthrough](../phase-10-semantic-matching.md). Final scoring remains module 11.
