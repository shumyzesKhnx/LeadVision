# 15 — Minimal browser interface

**Purpose:** make the complete reviewed workflow usable through plain forms and lists. **Requirements:** UI-01/02; FR-10/11/14/15; OUT-02/03; PIPE-01; AN-01; DATA-02 local display. **Dependencies:** 02–14 and backend Swagger acceptance. **Priority:** Must.

## Inputs and outputs

Inputs: operator form entries/API responses and all job/warning states. Outputs: same-origin HTML/CSS/JavaScript interface for setup, campaign/lead entry, import, evidence analysis, knowledge, draft review, pipeline and dashboard. The UI communicates missing/stale evidence instead of hiding it behind a score.

## Future files and database changes

`frontend/index.html`; `frontend/css/app.css`; `frontend/js/api.js`, `state.js`, `setup.js`, `leads.js`, `analysis.js`, `knowledge.js`, `drafts.js`, `dashboard.js`; static mount in `backend/app/main.py`; `backend/tests/integration/test_static_routes.py`; `backend/tests/ui/test_operator_flow.py`. No new tables. No React, Next.js, Tailwind or frontend build pipeline.

## Endpoints

Use the shared API only; `/` serves interface. Route tabs/shared views are sufficient. This module adds no alternate business logic or filesystem endpoints. Avoid API/static catch-all collisions.

## Implementation steps

1. Build labelled agency/service/ICP/campaign forms and preserve entered values on 422/409 errors. Explain service versus target customer using simple help text.
2. Build manual lead form, CSV template/upload/results, paginated list with search/filter/sort, and explicit delete-confirm dialog. Disable duplicate submission while request is in flight; API uniqueness remains the final defense.
3. Build analysis controls for live/cached/uploaded evidence. Display source labels, collection/import times, screenshot thumbnail, usability-review action and evidence excerpts. Poll jobs with a bounded interval (proposed 2 seconds), stop on terminal status/navigation and provide manual refresh after polling limit.
4. Show stage outcomes, partial failure, missing model/image/text, stale reasons and retry/recompute actions. Processing status and sales pipeline get separate labels.
5. Show score components, numeric score, coverage, Needs review, Ineligible, currentness, override reasons and caveats. Do not label cosine or coverage as confidence/probability. Show raw visual metrics beside screenshot and limitations.
6. Build knowledge pasted/TXT input and indexing/version state. Draft view presents source excerpts, claim checks, edit/save, review acknowledgment, approve/reject and approved copy. Clipboard failure offers select-and-copy text.
7. Show server-supplied pipeline transitions and required reasons. Dashboard filters match lead list; optional export/tags only appear if implemented.
8. Use textContent for untrusted text; create links only from validated HTTP/HTTPS source URLs. Do not interpolate model HTML. Add focused keyboard navigation, visible labels, required indicators and readable contrast. Render dates in Asia/Karachi with explicit timezone.
9. Include loading, success, empty, unavailable, partial and error states for each view; centralize API error interpretation and revision handling. Do not leave an infinite spinner after network failure.

## Errors and recovery

Network disconnect preserves form data and offers retry. API field errors focus the relevant field. 409 edit conflict reloads current revision without silently discarding typed text. Poll timeout offers resume, not false analysis failure. A missing model leaves setup/leads/evidence browsable. Delete confirmation is required before sending the API deletion request.

## Tests and acceptance criteria

Complete agency -> ICP -> campaign -> saved lead analysis -> grounded draft edit/approve -> manual pipeline update in a browser. Test rejected forms preserve values, submit buttons recover after errors, all processing states render, and approved draft copy does not send. HTML/script payloads from text/LLM render as inert text. Use keyboard through forms and dialogs. Confirm filtered counts and API errors readable; delete cancellation sends no DELETE. AT-01–11 have a UI smoke pass after their backend acceptance, while backend automated tests remain the main logic evidence.
