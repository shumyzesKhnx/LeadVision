# Shared API contracts

All paths below start with `/api/v1`. Serve static HTML separately at `/`. Swagger at `/docs` must support the core flow before the browser UI exists. Health, agency and service routes are implemented; the remaining routes are planned contracts.

## Conventions

- UTF-8 JSON, snake_case keys, UUID identifiers, ISO 8601 UTC times. Reject unknown request fields and model-output fields. Absent PATCH fields stay unchanged; explicit null clears optional fields. Required strings are trimmed and cannot be blank.
- `201` for new records, `200` for reads/edits/archive actions, `202` for accepted jobs, `204` for completed resource deletion without a body. A deletion with pending file cleanup returns `202` and a cleanup state. Errors: `400` malformed input, `404` missing entity, `409` duplicate/conflict/invalid transition, `413` size limit, `415` unsupported media, `422` invalid fields, `503` unavailable worker/runtime. Do not return `500` for an expected validation failure.
- Resource responses include `id`, `revision` where mutable, `created_at`, `updated_at`; sensitive internal paths and raw diagnostics are excluded. Resource edits, deletion, draft review and pipeline changes require `If-Match` containing the quoted edit revision returned in ETag (for example, `"3"`). Missing header returns `428 PRECONDITION_REQUIRED`; mismatched revision gives `409 EDIT_CONFLICT`. Job cancellation is an idempotent command without If-Match; job initiation/retry uses Idempotency-Key instead. Historical immutable records need no edit endpoint.
- Collections return `{items, page, page_size, total}`. Default page 1 and size 25, maximum size 100. Whitelist sort keys and directions; add ID tie-breaker. Filter before pagination. Score-null records sort last. Search is case-insensitive company-name substring.
- Mutations are same-origin JSON or bounded multipart uploads. Bind to `127.0.0.1`, disable broad CORS, check Host and Origin against configured loopback origins, reject hostile browser origins. Local scope does not remove website-to-local-server request risks. No public authentication claim is made.
- All queued POST requests require `Idempotency-Key`, 1–128 printable characters. Key scope includes operation and owner (`analysis:<lead_id>`, `index:<version_id>`, `outreach:<lead_id>`). Same key and canonical body hash returns same job, even if terminal; same key with different input gives `409 IDEMPOTENCY_CONFLICT`. Look up a replay before revalidating current versions or consuming its upload token again; an edit after job creation must not turn a legitimate replay into a second job. A new key while the same lead has active analysis gives `409 ANALYSIS_ACTIVE` with existing job ID.
- Optional `X-Client: n8n` records an informational activity origin from an allowlist; it grants no permissions and cannot select another agency. Default origin is `api` or the same-origin operator interface.

Error example:

```json
{
  "error": {
    "code": "INVALID_SIZE_RANGE",
    "message": "Minimum employees cannot exceed maximum employees.",
    "details": [{"field": "employee_min", "reason": "must_be_at_most_employee_max"}],
    "request_id": "server-generated-id"
  }
}
```

Worker errors add `stage` and `retryable` inside bounded details. API and poll responses do not include stack traces, arbitrary raw model responses, local paths or secrets. Request IDs correlate with local logs.

## Setup endpoints

| Owner | Method and path | Input | Output |
|---|---|---|---|
| 02 | `POST /agency` | name required; description/contact optional | 201 singleton agency; 409 if already exists |
| 02 | `GET /agency`; `PATCH /agency` | PATCH editable fields and If-Match | agency, including active service count |
| 02 | `GET /services`; `POST /services` | name, description | paginated services / 201 service |
| 02 | `GET /services/{id}`; `PATCH /services/{id}` | PATCH name/description/active and If-Match | service with edit ETag; inactive service retained historically |
| 03 | `GET /icps`; `POST /icps` | name, target_text, criteria, exclusions, desired_needs, weights, thresholds | ICP plus current version |
| 03 | `GET /icps/{id}`; `PATCH /icps/{id}` | edit fields, archived optional, If-Match | new immutable version if analytical config changed |
| 03 | `GET /icps/{id}/versions` | pagination | immutable history |
| 04 | `GET /campaigns`; `POST /campaigns` | name, icp_id, description optional | campaign with agency_id resolved from singleton |
| 04 | `GET /campaigns/{id}`; `PATCH /campaigns/{id}` | name/description/icp_id/archived, If-Match | campaign and count of affected stale leads |

ICP criteria use arrays of canonical industry labels and ISO country codes, optional explicit region definitions mapped to countries, `employee_min` and `employee_max`. Exclusions are `{industries:[], countries:[]}` and optional size rules with explicit bounds; free text goes in `preferences_text` and is never parsed into a hard rule. Default weights are `{industry:25, geography:20, size:15, semantic:40, visual:0}`. Thresholds are `{high:75, medium:50, minimum_coverage:0.6}`. Validate `0<=medium<high<=100`, `0<=minimum_coverage<=1` and all eligible weights. Visual activation requires calibration ID and a new configuration version.

## Lead and evidence endpoints

| Owner | Method and path | Input | Output |
|---|---|---|---|
| 05 | `POST /leads` | company_name, website, campaign_id; optional fields from FR-07 | 201 lead, provenance and possible-name-duplicate warning |
| 05 | `GET /leads` | campaign_id, pipeline_state, priority, q, sort=`score`/`created_at`, direction, pagination | lead rows with latest score, coverage, currentness and processing status |
| 05 | `GET /leads/{id}`; `PATCH /leads/{id}` | correction fields/notes, If-Match, optional correction_reason | detail / edited lead with stale reasons |
| 05 | `DELETE /leads/{id}?confirm=true` | If-Match | 204 or 202 cleanup pending; 409 while a job is active |
| 05 | `GET /imports/template` | none | CSV attachment with FR-08 column names |
| 05 | `POST /campaigns/{id}/imports` | multipart `file` UTF-8 CSV | row results and accepted/duplicate/invalid totals |
| 07 | `POST /leads/{id}/saved-evidence` | multipart `text` or TXT, image optional, source_type cached/uploaded, original_url, collected_at optional | validated opaque `upload_token`, hashes, warnings, expiry; no analysis yet |
| 07 | `GET /runs/{id}/evidence` | pagination | evidence records with labels and opaque artifact URLs |
| 07 | `GET /artifacts/{evidence_id}/image?variant=original\|thumbnail` | owned screenshot evidence ID | validated image stream; never arbitrary local path |
| 07 | `PATCH /evidence/{id}/review` | usable boolean, required reason when unusable, If-Match | evidence review and dependent stale reasons |

CSV line numbers start at 2 for first data row. Row result: `{row, status:"accepted"|"duplicate"|"invalid"|"not_processed", lead_id, errors, warnings}`. Normal validation results use the first three states. File-level validation failures import zero rows. A database/systemic error is not mislabelled as a bad CSV row: halt remaining rows, use not_processed for them, and include committed-row results and all four totals in the safe error details.

## Jobs, analyses and scores

| Owner | Method and path | Input | Output |
|---|---|---|---|
| 06 | `POST /leads/{id}/analysis-jobs` | `{mode:"live"|"cached"|"uploaded", upload_token?, include_supporting_pages:false}` and Idempotency-Key | 202 job receipt |
| 06 | `GET /jobs/{id}` | none | job status, kind, stage, stage counts, warnings, bounded errors, run/result ID |
| 06 | `POST /jobs/{id}/cancel` | none | cancellation request/state |
| 06 | `POST /jobs/{id}/retry` | new Idempotency-Key; optional fresh upload_token for saved analysis | new job using current inputs and retained validated saved evidence; retry_of ID; request new upload if evidence is unavailable |
| 06 | `GET /leads/{id}/runs`; `GET /runs/{id}` | pagination for history | snapshots, completed outputs and warnings |
| 11 | `GET /leads/{id}/scores`; `GET /scores/{id}` | pagination for history | score, components, sources, coverage, freshness, exclusion and recommendation |
| 11 | `POST /leads/{id}/overrides` | kind, value, reason, reviewer, score_id optional | independent recorded override; does not replace computed score |

Receipt: `{job_id,status,poll_url,run_id}`. Poll shape: `{id,kind,status,current_stage,progress:{finished_stages,total_stages},queued_at,started_at,finished_at,warnings,errors,result:{run_id?,draft_id?,knowledge_version_id?},retryable}`. Progress is stage count, not a fictitious accurate percentage of runtime. Completion may include missing score; see stage outcomes.

Score response distinguishes `score` (0–100 or null), `coverage` (0–1), `score_band` (High/Medium/Low or null), `priority` (High/Medium/Low/Needs review), `ineligible`, `is_current`, `recommended_for_qualification` and `overrides`. Each component contains state, value, configured/eligible/available weight, numerator and normalized contribution, source and explanation. UI rounds the total to one decimal but storage retains precision.

## Knowledge and outreach

| Owner | Method and path | Input | Output |
|---|---|---|---|
| 12 | `GET /knowledge`; `POST /knowledge` | JSON title, type, text, approved, fictional_demo | list / 201 document and version |
| 12 | `POST /knowledge/uploads` | multipart UTF-8 TXT, title, type, approved, fictional_demo | 201 document and version |
| 12 | `GET /knowledge/{id}`; `PATCH /knowledge/{id}` | edit text/title/type/approved/archived, If-Match | document/new version and indexing state |
| 12 | `POST /knowledge/{id}/index-jobs` | current version ID, Idempotency-Key | 202 job receipt |
| 12 | `POST /knowledge/retrieval-preview` | lead_id, service_id, analysis_run_id | up to 3 eligible chunks with similarity, or explicit empty reason |
| 13 | `POST /leads/{id}/outreach-jobs` | service_id, analysis_run_id, optional acknowledge_missing_analysis, Idempotency-Key | 202 draft job; current supported context required |
| 13 | `GET /leads/{id}/drafts`; `GET /drafts/{id}` | pagination | series, revisions, sources, review/freshness |
| 13 | `POST /drafts/{id}/revisions` | subject, body, claim_sources/removed_claims optional, If-Match | new Edited revision, never mutate approved text; validate sources belong to selected company/agency |
| 13 | `POST /drafts/{id}/review` | decision Approved/Rejected, reviewer, factual_review_acknowledged required for approval, reason optional (required reject), If-Match | new review revision with time |
| 13 | `GET /drafts/{id}/approved-text` | revision_id optional, must be Approved | plain text/JSON for manual copy |

Regeneration uses a new outreach job key and creates a new draft series. For the lean MVP, stale grounding blocks new approval: regenerate from current context, then edit/review the new series. Editing old text alone does not make its sources current. Preserve previously approved history with a stale warning. There is no `/send` endpoint.

## Pipeline, counts and optional features

| Owner | Method and path | Input | Output |
|---|---|---|---|
| 14 | `GET /leads/{id}/pipeline-transitions` | none | allowed next states, required reason/override warnings |
| 14 | `POST /leads/{id}/pipeline-events` | state, note, reason if required, If-Match | lead state and recorded event |
| 14 | `GET /leads/{id}/activities` | pagination | safe ordered history |
| 14 | `GET /dashboard` | campaign_id optional | total, counts by pipeline, High, processed, failed, active campaigns |
| 14 | `GET /leads/export` | same filters as list | formula-safe CSV; route registered before `/{id}` |
| 14 | `PATCH /leads/{id}/tags` | optional Should: tags array, If-Match | normalized tags |
| 16 | `GET /runs/{id}/visual-reference-comparison` | optional Should | experimental CNN neighbours and limitations |
| 01 | `GET /health` | none | DB, worker, configured runtime readiness; no absolute paths or secrets |

ML experiments have no production endpoint. n8n uses the existing analysis and poll endpoints. Backup/restore is a local command workflow, not an unrestricted API filesystem operation.
