# 14 — Pipeline, activities, dashboard and export

**Purpose:** record human sales decisions and show counts that match stored leads. **Requirements:** PIPE-01/02; AN-01; EXP-01 (Should); FR-10; SCORE-03/04 manual decisions. Tags are a Should scope item on SRS page 3 with no separate ID. **Dependencies:** 11, 13. **Priority:** Must pipeline/history/counts; Should export/tags.

## Inputs and outputs

Inputs: lead state-change request, optional note, required reopen/override reason, campaign/list filters, actor/origin. Outputs: explicit state changes and activity events, allowed transitions, consistent dashboard counts, optional sanitized CSV/tags. Converted means operator-reported success, not verified revenue.

## Future files and database changes

`backend/app/modules/pipeline/pipeline_schema.py`, `dashboard.py`; `backend/app/modules/pipeline/pipeline_service.py`, `dashboard.py`, `lead_export.py`; `backend/app/modules/pipeline/analytics_repository.py`; `backend/app/modules/pipeline/pipeline_api.py`, `activities.py`, `dashboard.py`, `exports.py`; optional `backend/app/modules/pipeline/lead_tag_model.py`; migration `015_pipeline_indexes_tags.py`; `backend/tests/unit/test_transitions.py`, `test_csv_export_safety.py`; `backend/tests/integration/test_dashboard_counts.py`, `test_activities.py`.

Use existing lead pipeline state, activities and overrides; add indexes. Optional tags have UNIQUE lead/tag rows. State and event commit in the same transaction. Unique event keys prevent retries duplicating activities. Approved outreach does not change state.

## Endpoints

`GET /leads/{id}/pipeline-transitions`; `POST /leads/{id}/pipeline-events`; `GET /leads/{id}/activities`; `GET /dashboard`; optional `GET /leads/export`, `PATCH /leads/{id}/tags`. Export reuses list filters and excludes private artifact paths/secrets. Revision checks protect state updates.

## Proposed transition rules

| Current state | Allowed next states | Notes |
|---|---|---|
| New | Reviewed, Lost | Review is explicitly chosen |
| Reviewed | Qualified, Contacted, Lost | Contacted can record manual outreach without score recommendation |
| Qualified | Reviewed, Contacted, Lost | Back to Reviewed for reconsideration |
| Contacted | Reviewed, Replied, Lost | Correction/backtracking requires reason |
| Replied | Reviewed, Converted, Lost | Conversion is manually reported |
| Converted, Lost | Reviewed | Reopen requires nonblank reason |

Same-state submission is rejected `409 NO_STATE_CHANGE`. Other jumps are invalid. All backward/correction transitions require a reason. Normal transitions accept optional note. Entering Qualified with hard exclusion requires existing reasoned exclusion override; with stale/missing/coverage below the saved minimum requires explicit manual qualification override acknowledging warnings. Bind overrides to the relevant score/input/config fingerprint; they cannot silently carry forward to changed criteria or facts. A High recommendation alone never changes state. These are proposed technical transition choices because the SRS delegates exact rules to design.

## Implementation steps

1. Implement the transition table in one service shared by API and UI. Return allowed states plus reason/override requirements, not a second frontend-only rule set.
2. Apply state change with expected revision and activity. Reviewer overrides are independent records; qualification still records a manual event.
3. Consolidate earlier events: creation, row import, research job, scoring run, corrections, draft reviews and status changes, with time/origin. Keep analysis job events distinct from sales status events.
4. Query dashboard from the same filtered lead set. Define total = all matching leads; pipeline counts partition total. High = latest **current** score with displayed High priority, including separate exclusion indicator. Processed = latest analysis status completed or partial. Failed = latest analysis status failed. Cancelled/queued/running are neither processed nor failed; never count historical retries as extra leads.
5. Active campaigns = nonarchived campaigns in the selected campaign set (0 or 1 when a single campaign is selected). With no campaign filter count all active campaigns. Archived campaign leads remain visible if selected explicitly.
6. Implement Should CSV with current score/coverage/priority/status and source labels. Quote through a CSV writer; neutralize formula prefixes `=`, `+`, `-`, `@` and leading control/whitespace variants with a leading apostrophe before writing. No internal paths or diagnostics.
7. Optional tags are bounded text labels, not a new scoring input. Document them separately if deferred.

## Errors and recovery

`INVALID_TRANSITION`, `REOPEN_REASON_REQUIRED`, `QUALIFICATION_OVERRIDE_REQUIRED`, `EDIT_CONFLICT` are safe 409/422 responses. Count query failures report unavailable dashboard, never zero fabricated totals. Export failure returns no misleading successful file. Failed state/event commit rolls back both.

## Tests and acceptance criteria

Test every allowed/disallowed transition and terminal reopen reason. Approving a draft or completing analysis leaves pipeline unchanged. Retry key yields one activity and latest-job counts remain one per lead. Populate two campaigns with current/stale/partial/failed runs; exact filtered counts match direct DB assertions, and pipeline sum equals total. Formula/control-prefix cells are inert in exported CSV. AT-10 requires correct manual history and counts; optional export absence is reported honestly.
