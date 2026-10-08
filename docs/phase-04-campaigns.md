# Phase 4 — Campaigns

A **campaign** is a named group of prospects that uses one ICP. For example, “Website redesign prospects” can use your Pakistan software-company ICP. A campaign does not search the internet; you will add/import its companies in Phase 5.

Your flow is now: **agency → services → ICP → campaign → leads (next phase)**.

## Quick manual check

1. Refresh [Swagger](http://127.0.0.1:8000/docs).
2. Execute **GET /api/v1/icps**. Under **Response body → items**, choose a profile with `archived: false`. Copy its top-level `id`. Do not copy the agency ID or `current_version.id`.
3. Open **POST /api/v1/campaigns → Try it out**. Replace the entire request body below, putting your copied ICP ID inside the quotation marks:

   ```json
   {
     "name": "Website redesign prospects",
     "icp_id": "PASTE-YOUR-ICP-ID-HERE",
     "description": "Companies we want to evaluate for website redesign."
   }
   ```

   `PASTE-YOUR-ICP-ID-HERE` is a placeholder; replace it with the real UUID before executing. Expect **201**. Your response includes a new campaign `id`, `revision: 1`, the selected ICP and `analysis_allowed: true`.
4. Execute **GET /api/v1/campaigns**. Scroll to **Response body → items** to see your saved campaign. Expect **200**.

That is enough for the basic manual check. For the remaining checks, run:

```powershell
.\scripts\test.ps1
```

Expect **145 passed**. Tests use temporary data and leave your real campaign unchanged.

## Optional edits

Use **PATCH /api/v1/campaigns/{campaign_id}**. In the path field, paste the campaign ID without quotes. In **If-Match**, enter its current quoted revision, such as `"1"`.

| What you want | Request body |
|---|---|
| Rename | `{"name": "Updated campaign name"}` |
| Clear description | `{"description": null}` |
| Archive | `{"archived": true}` |
| Reactivate | `{"archived": false}` |
| Select another active ICP | `{"icp_id": "REPLACE-WITH-ANOTHER-ICP-ID"}` |

Expect **200**. A real change increases the revision; use the returned revision for the next edit. An old revision returns **409 EDIT_CONFLICT**; missing If-Match returns **428**. Saving identical values keeps the existing revision.

Archived campaigns disappear from the default list. Set **include_archived=true**, Execute and scroll to **Response body → items** to see them. They remain readable by ID and retain their activity history. There is no hard-delete endpoint.

If the selected ICP is archived, the campaign stays readable but shows `analysis_allowed: false` and `analysis_blocked_reason: ICP_UNAVAILABLE`. Reactivate that ICP or choose another active one. A campaign cannot be reactivated with an unavailable ICP. Archived campaigns use `CAMPAIGN_ARCHIVED` as their blocked reason.

## What the response means

- `icp_id`: the profile this campaign uses.
- `current_icp_version_id` and `current_icp_version`: the selected profile's current analytical configuration. These update when its criteria change, without changing the campaign's own edit revision.
- `analysis_allowed`: campaign and ICP pass selection checks. Actual analysis endpoints arrive in Phase 6; this field does not mean analysis is implemented now.
- `lead_count`: Phase 5 now reports the actual saved lead count, including leads in archived campaigns.
- `invalidation.targeting_changed`: true on the response to an ICP switch. It describes that edit, not permanent status. Phase 5 reports the campaign's actual lead count as `affected_leads` on an ICP switch; real result invalidation follows with analysis/scoring.

ICP configuration edits now return the real number of linked campaigns in `invalidation.affected_campaigns`. Result counts remain 0 until analysis/scoring is implemented. Later runs must snapshot their selected ICP/version; the shared currentness helper detects an ICP switch, newer version or archive without rewriting history.

## Verification and scope

Implemented FR-06, campaign persistence portion of AT-01, DATA-01/02 relationships and the campaign/configuration portion of FR-05. **145 automated tests passed**, including the previous 126 checks. They cover two independent campaigns, input validation, missing/archived ICPs, revision conflicts, null handling, archive/reactivation, work-preflight guards, ICP switches/version changes, activity rollback, competing edits, restart persistence and database foreign keys.

Migration 004 adds campaigns and their activity foreign key. The activity/cleanup table rebuild preserves existing cleanup links; an orphan legacy campaign reference causes rollback. The existing database was snapshotted before upgrading. Live health, Swagger, OpenAPI and campaign listing returned **200**, with application **0.4.0** and schema **4**. Fingerprints of all prior agency/service/ICP/version/activity/cleanup/maintenance records matched before and after upgrading, and the foreign-key check was clean.

Actual imports, jobs, historical lead counts, score invalidation, queued-job archive checks and dashboard counts are tested when Phases 5/6/11/14 implement those features. No example campaign is inserted into your real database by implementation tests.

Next: **Phase 5 — companies/leads and CSV import**.
