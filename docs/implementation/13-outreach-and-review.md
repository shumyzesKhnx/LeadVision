# 13 — Outreach drafting and human review

**Purpose:** prepare grounded text and preserve every edit/review without sending it. **Requirements:** OUT-01–03; RAG-03/04; FR-02/20/21; DATA-02; PIPE-02; AT-09. **Dependencies:** 11, 12. **Priority:** Must.

## Inputs and outputs

Inputs: lead, selected active service, current supported company context/run, usable observations, retrieved approved chunks, optional verified contact name, model/prompt config. Outputs: subject/body with claim-source map, retrieval IDs/scores, immutable generation/edit/review revisions, reviewer/time, visible grounding warnings and approved manual-copy text.

## Files and database changes

`backend/app/modules/outreach/outreach_model.py`; `backend/app/modules/outreach/outreach_schema.py`; `backend/app/modules/outreach/outreach_repository.py`; `backend/app/modules/outreach/outreach_service.py`, `draft_grounding.py`, `draft_review.py`; `backend/app/modules/outreach/outreach_v1.txt`; `backend/app/modules/outreach/outreach_api.py`; migration `backend/app/modules/foundation/014_outreach.py`; `backend/tests/unit/test_draft_validation.py`; `backend/tests/integration/test_draft_history.py`, `test_grounded_fallback.py`.

Create `outreach_drafts`, `outreach_revisions`, `draft_sources`. Regeneration creates a new draft series. Editing creates a new text revision. Approval/rejection creates an immutable review revision copying the reviewed text. Retain service/company/knowledge snapshots so the reviewer can inspect the historical claim basis.

## Endpoints

`POST /leads/{id}/outreach-jobs`; `GET /leads/{id}/drafts`; `GET /drafts/{id}`; `POST /drafts/{id}/revisions`; `POST /drafts/{id}/review`; `GET /drafts/{id}/approved-text`. Initiation is queued/idempotent. Review identifies current revision with If-Match; stale concurrent review cannot approve the wrong text. There is no sending endpoint or email integration.

## Implementation steps

1. Check active service and current company grounding. A partial run may draft from its supported context with explicit `acknowledge_missing_analysis`; missing visual metrics need not block text. Reject stale selected context until recomputed/reviewed.
2. Retrieve through module 12 and snapshot source IDs, versions, scores, exclusions and threshold. If empty, use verified service descriptions and no case-study/client/statistical claims.
3. Assemble versioned prompt with company evidence, service and up to three chunks. Use generic greeting unless contact name is verified. Request 80–150 body words by default, concise subject, claim list with allowed source IDs, and hypothesis labels for possible improvements.
4. Validate strict JSON/length/schema and each source/claim reference before persistence. Proposed caps: subject 200 characters/body 2,000; enforce target word range or warn with repair budget. Reuse module 08's bounded one-recovery policy. Numerical/client/achievement claims require explicit source support.
5. Deterministic validation checks citations and obvious unsupported numbers/names, but cannot prove natural-language entailment. Show all factual claims for human review; do not label drafts factually verified merely because JSON passed.
6. Persist new Draft series/revision transactionally. Render source-linked generated text with a factual-review label. Respectful visual language only: measured observations may suggest a review area, never establish “bad website” or buying intent.
7. Allow edit/save to new Edited revision. Preserve source snapshots, mark changed factual sentences as requiring review, and let reviewer associate new claims with supported sources or remove them. Approval requires an explicit factual-review acknowledgment, reviewer label, current revision and no unresolved unsupported claim marker.
8. Approved/rejected text is immutable. Edits after approval create a new Edited revision needing fresh approval; old approval stays inspectable. Regeneration never overwrites approval. Reject requires reason; approval records local operator identity label and UTC time, not a public authenticated identity claim.
9. Knowledge/service/company changes show stale-grounding warnings on previous drafts. Previously approved history remains; for the lean MVP, regenerate from current context before a new approval. Editing old text does not refresh old sources. Copy route returns only an explicitly Approved revision and includes its stale warning if applicable. Approval/copy never sends or changes pipeline.

## Errors and recovery

`409 NO_ACTIVE_SERVICE`, `CONTEXT_STALE`, `CONTEXT_MISSING`, `REVIEW_CONFLICT`, `UNRESOLVED_CLAIMS`; `MODEL_UNAVAILABLE`, `DRAFT_OUTPUT_INVALID`. A generation failure creates no partial unvalidated draft. Keep prior drafts and successful retrieval snapshots/job diagnostics. Invalid edit preserves user text in UI and returns field errors.

## Tests and acceptance criteria

Generate, edit and approve; compare preserved text/revisions and reviewer/time. Regenerate creates separate series; approve old revision race is rejected. Empty retrieval yields service-only message with no invented case study. Missing contact uses generic greeting. Unsupported claim prevents unchecked approval; source review/edit resolves it. Service removal or knowledge archive retains approved text but shows warning. Review at least five actual model drafts, count unsupported factual claims and require zero in final approved demo drafts. AT-09 confirms no external messaging and no automatic Contacted transition.

## Implemented behavior

The company page now offers draft preparation, editing, factual review, revision history and copying of the current approved text. Source passages stay collapsed until requested. Retrieval is a separate saved job stage, so it remains inspectable if generation fails. Two invalid model answers produce a clearly labeled, validated service-introduction template; it does not include case studies. Model transport/timeouts remain failures. Reviewed text is never sent automatically. Configuration uses the existing Qwen model with 8192 context tokens and 1536 output tokens by default.
