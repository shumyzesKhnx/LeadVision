# Phase 2 — Agency and services

Module 02 is implemented. Requirements: FR-01, FR-02, agency persistence portion of AT-01, plus shared API validation and errors. Schema version is **2**. Your agency tells the system who you are; a service tells it what you sell.

## Try it in Swagger

Open [Swagger](http://127.0.0.1:8000/docs) and refresh the page. You will see **Agency** and **Services** sections.

1. Expand **POST /api/v1/agency**, select **Try it out**, replace the body with this example, then select **Execute**:

   ```json
   {
     "name": "TechNova",
     "description": "We help businesses improve their websites."
   }
   ```

   Use your own agency name if you prefer. A **201** response means the profile was created. Creating another profile returns **409 AGENCY_EXISTS** because this app has one workspace.

2. Expand **POST /api/v1/services** and submit:

   ```json
   {
     "name": "Website redesign",
     "description": "We redesign business websites to improve their presentation."
   }
   ```

   You should get **201**, a service `id`, `active: true` and `revision: 1`. Add SEO or other services using the same endpoint.

3. Execute **GET /api/v1/agency** and **GET /api/v1/services**. The agency shows `active_service_count`; the service list is paginated. Defaults show active services. Set `include_inactive=true` to include deactivated records.

4. To edit the agency, use **PATCH /api/v1/agency**. Enter the current quoted revision in **If-Match**, for example `"1"` (including both quotes), and submit only the fields you want to change:

   ```json
   {"description": "Updated agency description."}
   ```

   The response has the next revision and an **ETag** header. Use the new value for the next edit. An old revision returns **409 EDIT_CONFLICT**; a missing If-Match returns **428**. Reload with GET before retrying.

5. To deactivate a service, use **PATCH /api/v1/services/{service_id}**. Paste its ID, enter its current quoted revision, and submit:

   ```json
   {"active": false}
   ```

   The service stays saved and remains accessible through **GET /api/v1/services/{service_id}**. Reactivate with `active: true` using the latest revision. Deactivation does not erase history. The last active service may be deactivated; future outreach requires an active service.

You can stop/restart the server and these records remain. The server is already running after implementation; do not start a second copy on port 8000. For future sessions, start with `scripts/start.ps1` from the project root.

## Contact and edit rules

Agency `contact` is optional and accepts `email`, `phone` and an HTTP/HTTPS `website`. Email checks basic syntax, not mailbox existence. Unknown fields are rejected. Blank names and blank service descriptions are invalid.

Omitted PATCH fields stay unchanged. Set agency `description` or `contact` to null to clear it. Sending a contact object replaces the complete contact object; include every contact detail you want to retain. Required names, service descriptions and active flags cannot be null. Saving identical values does not create another revision/activity.

ETag tracks that record's edit revision. Related active-service count can change without changing the agency profile revision. Editing an old form never silently overwrites newer data.

## Verification

- **90 automated tests passed in 2.93 seconds**, including the 62 foundation checks.
- Live server check: health, Swagger and OpenAPI returned **200**; health reported application version **0.2.0** and schema version **2**, and OpenAPI included the agency/service routes.
- Tested agency uniqueness, required fields, contact validation, service ownership, active counts, pagination, null handling, revision headers, concurrent edits and restart persistence.
- Injected activity failures: the corresponding profile/service change rolled back too.
- Migration 002 preserves existing events, file-cleanup links and maintenance state while adding agency/service constraints. Invalid legacy references cause a full rollback instead of lost history.
- Service IDs/revisions are preserved on deactivation. Actual approved-draft retention and draft-staleness checks will be integrated in module 13, when draft tables exist. This module does not claim that outreach is implemented.

Next: **03 — ICP and scoring configuration**, where you define the customers your agency wants to target.
