# 12 — Agency knowledge and retrieval

**Purpose:** retrieve approved agency facts to ground outreach. **Requirements:** RAG-01–04; SEM-05; DATA-01–03; API-02–04; NFR-01/05/07; AT-08. **Dependencies:** 02, 06, 10. **Priority:** Must.

## Inputs and outputs

Inputs: title/type, approved agency text or UTF-8 TXT <=1 MB, fictional-demo label, selected company context/service, embedding/chunk config. Outputs: immutable document versions, bounded overlapping chunks and vectors, indexing job status, up to three eligible source chunks with similarity, or explicit empty retrieval reason. PDF ingestion is deferred.

## Implemented files and database changes

All backend files sit directly in `backend/app/modules/knowledge/`: `knowledge_model.py` defines records; `knowledge_schema.py` validates inputs; `knowledge_api.py` exposes endpoints; `knowledge_service.py` saves versions, approvals and jobs; `chunking_service.py` splits passages using LangChain and the embedding tokenizer; `knowledge_index_service.py` builds indexes; `retrieval_service.py` filters and ranks sources. Migration `foundation/013_agency_knowledge.py` adds persistence. `frontend/modules/knowledge/index.js` provides the screen. `backend/tests/integration/test_knowledge.py` verifies the lifecycle and exclusions.

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

`413 KNOWLEDGE_TOO_LARGE`, `415 UNSUPPORTED_DOCUMENT`, `422 INVALID_UTF8/EMPTY_DOCUMENT`, `409 VERSION_CHANGED`, `EMBEDDING_UNAVAILABLE`. Index failure keeps document and diagnostic job state but does not expose partial chunks. Wrong model revision excludes incompatible passages, reports `excluded_incompatible`, and offers reindexing. Archive is not deletion of draft citation history.

## Tests and acceptance criteria

Relevant approved fixture chunk is retrieved; other agency, unapproved, archived and superseded versions never rank. Edit while indexing and verify old job cannot publish itself as current. Test <=3 result cap, threshold/ties, overlap and tokenizer limits. Invalid UTF-8/PDF/oversized upload rejected before storage. Empty retrieval explicitly returns no sources and module 13 produces no case-study claim. Ordinary tests use fake vectors; separate pinned-model evaluation reports actual retrieval relevance. AT-08 passes with version filtering and grounded fallback evidence.


## Current behavior and boundaries

Verification: 416 regression tests pass, including the isolated Chrome journey for adding, approving, indexing, retrieving and editing knowledge, and populated schema 11/12 migration preservation/rollback. No evaluation documents were inserted into the user's workspace. LangChain splitter reference: https://reference.langchain.com/python/langchain-text-splitters/character/RecursiveCharacterTextSplitter.

The Knowledge screen supports pasted text and UTF-8 TXT uploads. New material needs explicit review; changing title, type, text or demo status creates a new unapproved version. Approval/activation changes invalidate previous indexes, so index again after reactivation. Limits: 1 MB of UTF-8 text, 100 documents, 100 versions per document and 1,000 passages per index. LangChain targets 180 tokens with up to 30 tokens of overlap; every passage is checked with the MiniLM tokenizer and exact source offsets. Indexing shares the existing worker, cancellation and polling endpoints; vectors reuse the SQLite embedding cache. Passages are published atomically and remain ineligible until the job completes.

Preview accepts explicit user-entered `query_text`, or a `lead_id` with an entered description, plus an optional active `service_id`. Long queries are rejected instead of silently truncated. `include_demo` defaults to false. The raw cosine threshold is 0.30; at most three source passages are returned with document/version/chunk IDs and visible demo labels. This threshold is an initial setting, not measured retrieval precision. Generation and outreach remain module 13 work; this module never drafts messages.


Initial installed-model check: three fictional documents and two queries retrieved the expected first source (website redesign cosine 0.766636; tax/accounting 0.642005). Long English, repeated paragraphs and Urdu text remained within 180 tokens with exact offsets. One unrelated secondary passage passed 0.30, so retrieval still needs reviewer judgment and broader relevance evaluation; this is not a precision benchmark. Evaluation artifacts stay in ignored `.cache/knowledge-trial/`, separate from user records.
