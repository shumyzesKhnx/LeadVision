# Frontend walkthrough

Open **http://127.0.0.1:8000/**. Use **http**, not https. Your existing records
appear automatically. You do not need to copy IDs or use Swagger.

If the server is already running, stop its terminal with **Ctrl+C** and restart
once to load the new interface. Do not launch a second server on the same port.

```powershell
cd E:\LeadVision
.\scripts\start.ps1
```

For research, keep a second terminal running:

```powershell
cd E:\LeadVision
.\scripts\worker.ps1
```

The Overview screen shows database, worker and local model readiness. If a
worker is already running, keep it; you only need one. No frontend installation
or npm command is required.

## A short demonstration for your instructor

1. **Overview:** show your records and system readiness.
2. **Agency & services:** show who your agency is and what it offers. You can
   edit a service, deactivate it and activate it again.
3. **Customer profiles:** show your ideal client's location, industry, size and
   needs. PK means Pakistan. A Pakistan agency can target Pakistan, the UK or
   another country; this setting describes clients.
4. **Campaigns:** open a campaign to see its companies. A campaign groups leads
   under one customer profile.
5. **Companies & research:** open Arbisoft or another company you added, then
   choose **Start research**. Live mode collects its website text and screenshot.
   Watch each processing stage. Collection and local AI may take some time.
6. **Results:** show the business summary and supporting quotes, similarity,
   screenshot measurements, saved evidence and explained score. Open **Why
   this score?** to see each component and its weight.
7. **How it works:** explain frontend → API → database, with a separate worker
   doing the research.

Run research before the demonstration so you have a saved result ready to
show. History retains previous attempts. Refreshing or reopening the page
does not erase them. Some websites block collection; a partial result shows
the error and retains the parts that succeeded.

## Using saved evidence

Choose **Saved files** in Start research. Upload actual website text as a UTF-8
`.txt` file and/or an actual PNG/JPEG screenshot. Text must be at most 1 MB;
the image at most 10 MB. Cached mode identifies previously collected evidence.
These sources are labeled separately from live collection. You can mark saved
evidence unusable with a reason and rerun when inputs change.

## Reading the results

- **Score:** the match with your customer profile, based on available evidence.
- **Coverage:** how much selected scoring information was available.
- **Unknown:** a missing fact, not an invented value.
- **Needs review / outdated:** review the evidence or rerun with current inputs.
- **Opportunities:** AI hypotheses, not confirmed needs.

This interface covers the completed workflow through explained scoring.
Automatic internet-wide discovery, knowledge retrieval, outreach and pipeline
transitions are future work. Visual measurements are descriptive; visual scoring
requires reviewed calibration. The current UI handles common targeting settings;
advanced region/calibration configuration remains available through the API.

## Files and verification

`frontend/index.html` is the page shell and `frontend/app.js` connects screens.
Each feature now has its own folder in `frontend/modules/`; shared controls,
API requests, state and the theme live in `frontend/shared/`.
The backend follows the same convention in `backend/app/modules/`.
See [the module folder guide](project-structure.md). No database migration or
data reset was needed for this reorganization.

```powershell
.\scripts\test.ps1
```

Frontend tests check local asset serving and path isolation. A real headless
Chrome test creates agency → service → profile → campaign → company in its
own database, edits a company, uploads evidence, queues and cancels research,
checks correction history and confirmed deletion, and checks mobile width.
Worker readiness and missing-model detection are controlled in that UI test;
it does not fabricate AI results. It also runs real saved-evidence processing,
checks screenshot measurements and score explanations, and reviews evidence.
Existing backend tests verify the other processing and scoring cases.

Verification: the full suite passed all 397 tests. After the final result-display
changes, all 3 frontend tests passed again. A separate Chrome smoke check opened
the real workspace and existing company list without changing user records.
