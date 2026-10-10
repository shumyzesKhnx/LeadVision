# 05 — Leads, corrections and CSV import

**Purpose:** accept prospect companies safely, keep campaign identity consistent and report every import row. **Requirements:** FR-07–11, DATA-01/02, PIPE-02 creation/import events; AT-02. **Dependencies:** 04. **Priority:** Must.

**Status:** implemented for manual leads, CSV import, corrections/provenance, current list/detail and confirmed fact/activity deletion. See [Phase 5 walkthrough](../phase-05-leads-and-imports.md). Evidence/model/draft sections remain empty, scores null, priority Needs review. Module 06 must add active-job deletion guards; 07/11/13 must add owned artifact/result cleanup and real stale-result integration. Downstream portions of AT-02 remain deferred.

## Inputs and outputs

Inputs: company_name, website, campaign; optional industry, country, employee_count, contact_name, contact_email, description and notes; UTF-8 CSV with FR-08 columns. Outputs: New leads, user-provided provenance, duplicate warnings/errors, paginated details, row-level import report and stale reasons after corrections. Unknown optional values are null.

## Files and database changes

`backend/app/modules/leads/lead_model.py`, `company.py`, `lead_fact.py`; `backend/app/modules/leads/lead_schema.py`, `imports.py`; `backend/app/modules/foundation/urls.py`; `backend/app/modules/leads/leads_repository.py`; `backend/app/modules/leads/leads_service.py`, `csv_import.py`; `backend/app/modules/leads/leads_api.py`, `imports.py`; migration `005_leads.py`; `backend/tests/unit/test_url_identity.py`, `test_csv_validation.py`; `backend/tests/integration/test_leads.py`, `test_imports.py`.

Create `companies`, `leads`, `lead_facts`. Add campaign-company unique constraint and list indexes. New leads receive `New` pipeline state. Extend activities with lead FK and deduplicated creation/import event keys. Runtime artifact tables are added in later modules.

## Endpoints

`POST/GET /leads`, `GET/PATCH/DELETE /leads/{id}`; `GET /imports/template`; `POST /campaigns/{id}/imports`. Shared API defines fields, filters and confirmation. Lead detail composes available outputs; missing later-module sections are explicit empty sections, not fabricated analysis.

`GET /leads/{id}/facts` adds paginated immutable fact history. Detail responses expose current fact revisions and at most 25 recent activities with a total count. Mid-import systemic failures include the bounded 100-row report under `error.import_report`, not the generic 30-detail error list. Parsing validates the whole file before writing; each valid row commits in a short IMMEDIATE transaction, with campaign/work-preflight rechecked. This serialization plus the campaign-company unique constraint prevents duplicate races.

## Implementation steps

1. Implement URL identity normalization from the shared design. Preserve original URL. Reject invalid scheme, credentials, malformed hostname and literal forbidden IPs before storing. Hostname public-address checks occur again before any future network request.
2. Upsert shared company identity and insert lead under the DB unique constraint. Case/www/tracking variants collide within a campaign; cross-campaign entries remain separate. Flag exact normalized name matches for review, without merging them.
3. Store supplied fields as user-provided fact revisions. Validate employee count >=0, optional email syntax and known country vocabulary. Never copy inferred facts into manual records automatically.
4. Stream uploads with a 5 MB cap; decode UTF-8/UTF-8 BOM; parse standard CSV quoting. Require company_name and website headers before inserting any row. Reject duplicate header names and more than 100 data rows before import. Ignore extra columns with a report warning.
5. Validate every row independently. Commit accepted rows in short transactions/savepoints; report in-file duplicates and existing-domain duplicates with existing lead ID. Invalid rows retain row/field explanations. Do not discard earlier valid rows.
6. Add paginated search/filter/sort; use latest score only once per lead when module 11 exists. Register `/leads/export` before `/{id}` later. Handle null scores deterministically.
7. Corrections append facts, increment relevant input revision, preserve old source values and call freshness invalidation. Changing domain checks campaign duplication and reassigns company identity without mutating another campaign's company.
8. Lead deletion requires explicit confirmation and no active job. Implement database cascade ordering plus artifact-cleanup outbox with later modules' owned artifacts registered. Shared agency knowledge and campaign remain.

## Errors and recovery

`409 DUPLICATE_DOMAIN`, `CAMPAIGN_ARCHIVED`, `ANALYSIS_ACTIVE`; `413 CSV_TOO_LARGE`; `422 CSV_HEADERS_MISSING`, `CSV_ROW_LIMIT`, field-level errors; `415` for non-CSV. A race is caught by the unique constraint and translated into duplicate conflict. If storage fails mid-import, preserve committed-row results, mark unprocessed rows and return an explicit systemic failure rather than claiming every remaining row was invalid.

## Tests and acceptance criteria

Use a CSV containing valid, duplicate, invalid-size, missing-name, Unicode and quoted-comma records; every row receives exactly one result. Missing header and 101 rows import zero records. Test 5 MB boundary and invalid UTF-8. Verify www/case/default-port/query normalization, separate subdomains and cross-campaign duplicates. Correction preserves provenance and marks only dependent results stale. Pagination and sorting have no repeated records. Delete a fixture lead and verify owned DB/artifacts disappear while knowledge/campaign persist; delayed file cleanup is visible and retryable. AT-02 passes after downstream artifact deletion is integrated.
