# 04 — Campaigns

**Purpose:** group leads around an ICP without losing previous results when targeting changes. **Requirements:** FR-06, FR-05, DATA-01/02; AT-01. **Dependencies:** 03. **Priority:** Must.

**Status:** campaign management implemented; see [Phase 4 walkthrough](../phase-04-campaigns.md). Leads/jobs/scores/dashboard acceptance is completed in their owning later modules. Shared preflight/currentness helpers are implemented without claiming those future workflows exist.

## Inputs and outputs

Inputs: required campaign name, selected active ICP, optional description, archive/reactivation action. Outputs: campaign records with workspace/ICP references, current configuration label, historical lead count and stale-result counts.

## Files and database changes

`backend/app/models/campaign.py`; `backend/app/schemas/campaign.py`; `backend/app/db/repositories/campaign.py`; `backend/app/services/campaign.py`; `backend/app/api/campaigns.py`; migration `004_campaigns.py`; `backend/tests/integration/test_campaigns.py`.

Create `campaigns`; add activity campaign FK. Use RESTRICT for agency and ICP references, not cascading history deletion. New runs snapshot the selected ICP's current version; campaigns do not overwrite old run versions.

## Endpoints

`POST/GET /campaigns`, `GET/PATCH /campaigns/{id}`. PATCH supports `archived` and `icp_id` with `If-Match`. Listing filters archive state and paginates. No campaign hard-delete endpoint.

## Implementation steps

1. Validate nonblank bounded name and selected ICP existence, same workspace and active state.
2. Create/read/edit/list campaigns and append activity in the same transaction.
3. Archive without deleting leads, runs, evidence or drafts. Allow historical reads; block new lead imports and analysis until reactivated. This import restriction is a proposed usability rule beyond FR-06.
4. Reactivate explicitly and verify the ICP is usable before new analysis.
5. Changing ICP increments campaign revision and invalidates current scores/recommendations for its leads; invalidate semantic results because target input changed. Preserve old run snapshots.
6. Expose an `analysis_allowed` indicator and reason to Swagger/UI. Job preflight rechecks it so the UI is not the enforcement point.

## Errors and recovery

Missing ICP: `404 ICP_NOT_FOUND`; wrong-workspace or archived ICP: `409 ICP_UNAVAILABLE`; blank name: field-specific `422`. Active job handling follows shared design: queued analysis does not start after archive, already-running historical work can finish with currentness checked. Reject stale edits with `409 EDIT_CONFLICT`.

Implemented ownership lookup returns the same `404 ICP_NOT_FOUND` for missing/foreign-workspace IDs; it does not reveal another workspace's records. Archived ICPs return `409 ICP_UNAVAILABLE`. No-op edits keep their revision. Reactivation requires an active ICP. Campaign FK ownership is also enforced by `(agency_id,icp_id)` referencing `(icps.agency_id,icps.id)`.

## Tests and acceptance criteria

Create two campaigns and verify independent leads and selected ICPs. Restart preserves linkage. Archive leaves all detail/history accessible, blocks new analysis and does not count as active in dashboard. Reactivate permits a new job. Swap ICP and verify old version references remain unchanged while new recommendations require recomputation. This completes campaign coverage of AT-01; processing checks finish with module 06.
