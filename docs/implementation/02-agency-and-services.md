# 02 — Agency and services

**Status:** implemented; see [walkthrough and verification](../phase-02-agency-and-services.md). Draft-history integration remains a module 13 check.

**Purpose:** remember what the agency is and what it sells. **Requirements:** FR-01–02, DATA-01–02, API-01/04; contributes AT-01 and OUT-01. **Dependencies:** 01. **Priority:** Must.

## Inputs and outputs

Inputs: required agency name; description and optional business contact details; required service name and description. Outputs: persistent singleton profile, active/inactive services, revision numbers and activity events. An active service is a prerequisite for outreach, not for adding leads.

## Future files and database changes

`backend/app/models/agency.py`, `service.py`; `backend/app/schemas/agency.py`, `service.py`; `backend/app/db/repositories/agency.py`, `service.py`; `backend/app/services/agency.py`, `service_catalog.py`; `backend/app/api/agency.py`, `services.py`; migration `002_agency_services.py`; `backend/tests/integration/test_agency_services.py`.

Create `agencies` and `services` as defined in the schema. Enforce one agency with a singleton constraint. Service removal is soft deactivation; retain identifiers, previous draft snapshots and review history. Extend activity agency FK.

## Endpoints

`POST/GET/PATCH /agency`; `GET/POST /services`; `GET/PATCH /services/{id}`. Requests and statuses follow shared API contracts. Lists optionally include inactive services. `PATCH` checks `If-Match`. No public registration or second workspace endpoint is planned.

## Implementation steps

1. Validate trimmed required names, bounded descriptions and optional explicitly supplied business contact details. Proposed max lengths: name 200, description 5,000, email 254 characters.
2. Add singleton create/get/update transactions. A second create returns conflict rather than another agency.
3. Add service create/list/edit/deactivate/reactivate. Resolve agency from the workspace; do not trust an arbitrary agency ID supplied by a client.
4. Record changes with actor/origin and revision, using safe bounded activity values.
5. Return active service count so later outreach preflight can explain its prerequisite.
6. Service edits mark dependent draft grounding stale once drafts exist; approved historical text is retained. The shared invalidation service can be introduced here with later dependency registrations.

## Errors and recovery

Missing workspace: `404 AGENCY_NOT_FOUND`. Blank name: `422` with field detail. Second workspace: `409 AGENCY_EXISTS`. Missing service: `404`; stale edit: `409 EDIT_CONFLICT`. Deactivating the last service is allowed, but subsequent outreach fails `409 NO_ACTIVE_SERVICE`. A DB failure rolls back both change and activity.

## Tests and acceptance criteria

Create TechNova with Website redesign and SEO; restart and verify all fields remain. Attempt a second agency and a blank service name. Simulate competing edits and confirm the earlier revision is not overwritten. Deactivate a service and verify it disappears from active selection while remaining in history. Once module 13 exists, verify approved drafts survive service deactivation and a new draft using that service is rejected. These demonstrate FR-01/02 and the agency portion of AT-01.
