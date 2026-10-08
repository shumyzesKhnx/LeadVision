# Phase 5 — Add companies to your campaign

You now have an agency, services, an ICP and a campaign. This phase adds **companies you want to evaluate**. Each company record within a campaign is called a **lead**. Adding it does not fetch websites or start AI analysis yet.

Phase 7 update: lead deletion with saved evidence returns 202 while the worker processes file cleanup. Leads without evidence files still return 204. See [the saved-evidence walkthrough](phase-07-saved-evidence.md).

## Quick manual test

1. Refresh [Swagger](http://127.0.0.1:8000/docs).
2. Execute **GET /api/v1/campaigns**. Under **Server response → Response body → items**, copy your active campaign's `id`. Check `analysis_allowed: true`; reactivate its campaign/ICP if necessary.
3. Open **POST /api/v1/leads → Try it out**. Replace the entire body with:

   ```json
   {
     "company_name": "Demo Software Company",
     "website": "https://example.com",
     "campaign_id": "PASTE-YOUR-CAMPAIGN-ID-HERE",
     "industry": "software",
     "country": "PK",
     "employee_count": 35
   }
   ```

   Replace the campaign placeholder with the copied ID, keeping its quotes. Execute. Expect **201**, a new lead `id`, `pipeline_state: New` and `revision: 1`.
4. Execute **GET /api/v1/leads**. Find the company under **Server response → Response body → items**. Optional `campaign_id` limits the list to a campaign; `q` searches names, for example `Demo`.

These are fictional details for testing. Enter real company names/public websites before real research later. Reserved example subdomains used below are not working company websites.

## Try CSV import

Download a blank template with **GET /api/v1/imports/template**, or use the [demo CSV](examples/phase-05-companies.csv) in `docs/examples/phase-05-companies.csv`.

1. Open **POST /api/v1/campaigns/{campaign_id}/imports → Try it out**.
2. Paste the campaign ID in the path field without quotes.
3. Select **Choose File**, choose the demo CSV, then Execute.
4. Scroll to **Server response → Response body** for row results and totals.

| Status | Meaning |
|---|---|
| `accepted` | Saved, with a new lead ID. |
| `duplicate` | Website already in this campaign; existing lead ID returned. |
| `invalid` | Row needs correction; other valid rows still save. |
| `not_processed` | System failure stopped the import; row was not saved. |

After the manual example above, expect **accepted 1, duplicate 1, invalid 1**. The second company saves; the negative employee count is rejected. Re-importing produces duplicates for saved companies. If you skip the manual example, the initial import accepts two rows instead.

Files must be UTF-8 (BOM accepted), at most **5 MB / 5,000,000 bytes** and **100 data records**. `company_name` and `website` headers are required. Optional columns: industry, country, employee_count, contact_name, contact_email, description, notes. Empty optional cells remain missing. Header names are trimmed/lowercased; extra columns are ignored with a warning. Unicode names/quoted commas work. Missing/duplicate headers, invalid encoding/quoting and row-limit violations reject the file before saving anything. Empty separator lines are ignored; report row numbers count data records starting at 2 after the header.

## Optional editing and deletion

**Edit:** PATCH `/api/v1/leads/{lead_id}` with the lead ID without quotes and its current quoted revision in **If-Match**, such as `"1"`. Submit only changes:

```json
{
  "employee_count": 45,
  "correction_reason": "Corrected the employee count."
}
```

Expect **200** and the next revision. Optional fields can be cleared with null; company name/website cannot. GET `/leads/{lead_id}/facts` shows old and new entered values. They are labelled `user_provided`, not externally verified. Analytical corrections increment `analytical_input_revision`; notes/contact edits preserve it. No-op edits keep their revision. Actual result invalidation follows with analysis/scoring.

**Delete:** DELETE `/api/v1/leads/{lead_id}` with current quoted If-Match and `confirm=true`. Expect **204**, empty body. Lead facts and lead activities are deleted; the campaign and other campaigns' leads remain. A deletion event stays in campaign history. Only delete a test record you intend to remove.

## Rules and current limits

- One normalized website domain per campaign. Case, one `www.` prefix, scheme/path/query/port do not create new identities. Arbitrary subdomains stay separate. Original URLs are retained; normalized fetch URLs keep non-default ports and queries.
- Across campaigns, the same company has independent lead facts. Correcting one website never changes another campaign's details. Matching names only produce warnings; they do not merge records.
- Archived campaigns/unavailable ICPs block new leads/imports. Existing leads remain readable/correctable. Archived-campaign lists still expose their saved leads.
- Employee count is a nonnegative whole number; zero is valid and unknown is null. Country uses ISO codes such as `PK`/`GB`. Emails use basic syntax checks.
- Leads start **New** with no score, **Needs review** priority and **not_started** processing. All scores are currently null, so score sorting falls back to deterministic creation/ID ordering. Phase 11 adds real scores; Phase 14 adds pipeline changes.
- Detail responses contain current entered facts, at most 25 recent activities and an activity total. Fact history is paginated. Evidence/model outputs/score components/drafts remain empty until their modules exist.
- A mid-import systemic failure returns **503**, with all row results/totals under `error.import_report`. Earlier commits remain; current/remaining rows are not_processed. Raw diagnostics are excluded. Preflight archive failures before import return 409; an archive during import stops further commits and preserves the report.
- Phase 6 must add active-job deletion blocking. Phase 7 and later must register owned artifacts/results for deletion/cleanup. Those records do not exist yet; downstream artifact-deletion acceptance remains deferred. Current fact/activity deletion is implemented.

Run `scripts/test.ps1` for remaining checks; expect **215 passed**. This implements FR-07–09, current list/detail/correction portions of FR-10/11, DATA-01/02, creation/import portions of PIPE-02 and import portions of AT-02.

## Verification

**215 automated tests passed in 21.92 seconds**, including the previous 145 checks. New checks cover URL identity/private literals, domain/name duplicates, cross-campaign independence, provenance/corrections, search/pagination, confirmed cascade deletion, restart persistence, concurrent duplicate creation, UTF-8/BOM, mixed imports, file-level rejection, exact size boundary, oversized/chunked uploads and systemic partial-import reports. Migration 004 → 005 preserves cleanup links and rolls back invalid legacy lead references.

The real database was snapshotted before upgrading. Live Swagger, health, OpenAPI, lead listing and CSV template returned **200**, with application **0.5.0** and schema **5**. Exact fingerprints of every prior agency/service/ICP/version/campaign/activity/cleanup/maintenance record matched before/after; foreign-key checks were clean. No demo leads were inserted into your actual database. The only added dependency is pinned `python-multipart==0.0.32`; all previous dependency versions were retained.

Next: **Phase 6 — jobs and processing workflow**.
