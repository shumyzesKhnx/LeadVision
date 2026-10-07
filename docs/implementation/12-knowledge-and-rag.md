# 12 — Agency knowledge and retrieval

**Purpose:** retrieve approved agency facts to ground outreach. **Requirements:** RAG-01–04; SEM-05; DATA-01–03; API-02–04; NFR-01/05/07; AT-08. **Dependencies:** 02, 06, 10. **Priority:** Must.

## Inputs and outputs

Inputs: title/type, approved agency text or UTF-8 TXT <=1 MB, fictional-demo label, selected company context/service, embedding/chunk config. Outputs: immutable document versions, bounded overlapping chunks and vectors, indexing job status, up to three eligible source chunks with similarity, or explicit empty retrieval reason. PDF ingestion is deferred.

## Future files and database changes

`backend/app/models/knowledge.py`; `backend/app/schemas/knowledge.py`, `retrieval.py`; `backend/app/db/repositories/knowledge.py`; `backend/app/services/knowledge.py`, `knowledge_index.py`, `retrieval.py`; `backend/app/integrations/langchain_rag.py`; `backend/app/api/knowledge.py`; migration `012_knowledge.py`; `backend/tests/unit/test_chunking.py`; `backend/tests/integration/test_retrieval_versions.py`, `test_knowledge_upload.py`.

Create `knowledge_documents`, `knowledge_versions`, `knowledge_chunks`; use existing embeddings/jobs. Documents retain agency and approval/demo metadata. All old chunks are excluded as soon as current version changes, even while a new index is pending. Do not retrieve old content as an availability fallback.

## Endpoints

`GET/POST /knowledge`; `POST /knowledge/uploads`; `GET/PATCH /knowledge/{id}`; `POST /knowledge/{id}/index-jobs`; `POST /knowledge/retrieval-preview`. Text edit appends version, invalidates old retrieval and reports pending indexing. Archive and unapprove prevent retrieval immediately.

## Implementation steps

1. Validate title, type, UTF-8, file bytes/content and no blank text. Store pasted/uploaded content as data only. Require explicit approval before eligibility; fictional material must carry visible demo label.
2. Save document and version transactionally; no extraction from PDFs. Editing increments version even if only text changes; analytical metadata snapshots accompany it.
3. Choose token-aware LangChain splitter with proposed 180-token chunks/30-token overlap for the candidate embedding model, enforce actual tokenizer limit, and store document offsets/IDs. Record splitter version and settings; characterize splitting on short/long text.
4. Queue indexing through module 06. Build chunks/vectors in a staged state and expose them only when the full current version index is complete. Before commit, check that document is still current/active/approved; old job output stays historical but never eligible.
5. Build query from verified company description and selected service. Encode with same model space as eligible chunks. Filter by agency, current active approved document version and compatible completed index **before** ranking.
6. Use NumPy cosine ranking; deterministic ID tie-break. Retrieve at most three above proposed minimum raw cosine .30. This is an initial tunable threshold, not measured precision; record it with draft inputs and evaluate on fixture queries.
7. Return IDs, text, version, source label and similarity. Empty retrieval means no matching approved evidence, not model permission to invent examples. Service descriptions remain a valid separate fallback source.
8. LangChain adapter connects splitting, retrieval, prompt inputs and Ollama call for module 13; avoid extra vector DB or agent execution. Keep logic testable without a real model.

## Errors and recovery

`413 KNOWLEDGE_TOO_LARGE`, `415 UNSUPPORTED_DOCUMENT`, `422 INVALID_UTF8/EMPTY_DOCUMENT`, `409 VERSION_CHANGED`, `EMBEDDING_UNAVAILABLE`. Index failure keeps document and diagnostic job state but does not expose partial chunks. Wrong model revision returns empty with `INDEX_INCOMPATIBLE` and reindex action. Archive is not deletion of draft citation history.

## Tests and acceptance criteria

Relevant approved fixture chunk is retrieved; other agency, unapproved, archived and superseded versions never rank. Edit while indexing and verify old job cannot publish itself as current. Test <=3 result cap, threshold/ties, overlap and tokenizer limits. Invalid UTF-8/PDF/oversized upload rejected before storage. Empty retrieval explicitly returns no sources and module 13 produces no case-study claim. Ordinary tests use fake vectors; separate pinned-model evaluation reports actual retrieval relevance. AT-08 passes with version filtering and grounded fallback evidence.
