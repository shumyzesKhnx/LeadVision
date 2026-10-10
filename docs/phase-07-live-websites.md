# Live website collection

Your system can now visit a lead's website, collect readable text and capture a screenshot. These become evidence for the NLP, image measurements, semantic matching and explained score you already built.

**Agency/services → ICP → campaign → lead website → live collection → analysis → score.**

This finishes the live part of module 07. It researches websites you supply; automatic discovery of companies across the internet remains outside the agreed flow. Phase 12 knowledge/retrieval is next.

## Quick Swagger test

1. Open [Swagger](http://127.0.0.1:8000/docs). Check that the API and separate worker are running.
2. Execute `GET /api/v1/leads` and copy the ID of your Arbisoft lead, whose website should be `https://arbisoft.com`.
3. Execute `POST /api/v1/leads/{lead_id}/analysis-jobs`. Paste that lead ID without quotes into the path field. Enter a new `Idempotency-Key`, such as `arbisoft-live-1`, and this body:

```json
{
  "mode": "live",
  "include_supporting_pages": false
}
```

4. Copy the returned **job ID** into `GET /api/v1/jobs/{job_id}`. Execute again until it finishes. Website collection and the local model can take a few minutes. Check errors and warnings if the result is partial.
5. Copy the returned **run ID** into `GET /api/v1/runs/{run_id}` to see the analysis and `score_result`. Use `GET /api/v1/runs/{run_id}/evidence` to see the collected sources, URLs and collection times. Image and thumbnail URLs are provided there.

Start with the homepage only. Setting `include_supporting_pages` to `true` adds at most two discovered About/Services pages from the same host. It does not crawl the whole website.

Use a new idempotency key for a new request. Retrying a finished live job visits the website again; it does not claim older evidence is freshly collected. Saved upload/retry behavior stays unchanged.

## What can go wrong

| Result | Meaning and next step |
|---|---|
| `ACCESS_DENIED` / `ROBOTS_DISALLOWED` | The site blocks collection or disallows that page. Use approved saved evidence. |
| `UNSAFE_DESTINATION` | A request points to a private/local/reserved address. It is blocked. |
| `DNS_FAILURE` / `HTTP_FETCH_FAILED` | The address or connection could not complete. Retry later or upload saved text. |
| `PAGE_TIMEOUT` / `PAGE_TOO_LARGE` | Collection reached its time or size limit. Saved mode remains available. |
| `BROWSER_UNAVAILABLE` | Chrome could not capture the page. Check the installed browser or upload a screenshot. |
| `MODEL_OUTPUT_INVALID` | The AI summary failed validation. Valid collected evidence, semantic matching and scoring can still be retained. |

Screenshot failure preserves collected text and lets the other analysis stages continue. Missing images never produce a fabricated visual score. Consent overlays are warnings; detection is approximate, so review the screenshot. You can mark evidence unusable using the existing review endpoint.

The default capture browser is your installed Chrome. `LEADVISION_BROWSER_CHANNEL=msedge` in `backend/.env` selects installed Edge instead; restart the worker after changing it. Each capture uses a fresh headless browser context and records the actual browser version. No personal browser profile or login is used. A separate Chromium download is optional; this workspace's download timed out, and the Chrome configuration was checked instead.

## New files and storage

| File/folder | Purpose |
|---|---|
| `backend/app/modules/evidence/network_safety.py` | Validate all DNS answers and connect to the exact checked IP. |
| `backend/app/modules/evidence/safe_http_client.py` | Fetch bounded HTML with verified TLS and safe redirects. |
| `backend/app/modules/evidence/public_proxy_client.py` | Check browser destinations and bound transferred bytes. |
| `backend/app/modules/evidence/safe_browser_client.py` | Capture a 1366 × 768 screenshot through that proxy. |
| `backend/app/modules/evidence/live_evidence_service.py` | Respect robots instructions, gather text, reserve files and save sources. |
| `backend/app/modules/evidence/text_extraction_service.py` | Remove scripts/styles and repeated boilerplate while keeping readable text and source offsets. |
| `backend/app/modules/evidence/live_artifact_model.py` | Track ownership before writing live files, including interrupted writes. |
| `backend/app/modules/foundation/012_live_evidence.py` | Enable Live evidence and add durable file reservations. |
| `backend/tests/unit/test_network_safety.py`, `integration/test_live_evidence.py`, `test_browser_egress.py`, `test_live_migration.py` | Check private-address blocking, limits, real Chrome behavior and upgrade preservation/rollback. |

Existing endpoints handle live evidence; no separate collection API is needed. Text/image evidence is labelled **Live** with the actual URL and collection time. Uploaded and Cached sources retain their own labels. Internal file paths remain hidden.

Text fetching bounds each response to 2 MB, uses a 30-second request ceiling and allows at most five redirects. Compressed responses are rejected when the server ignores the uncompressed request. Extracted text is bounded to 30,000 characters per page and 26,000 characters across the stored combined text. Each page keeps its URL, title, excerpt, offsets and original HTML hash. This is a conservative extractor, not a complete JavaScript-rendered text reader.

The browser uses a validating proxy for HTTP and HTTPS CONNECT, including subresources; it never switches to a direct connection. Capture limits are 30 seconds, 100 routed requests, 32 concurrent proxy connections and 20 MB aggregate proxy traffic. Encrypted tunnel bytes count toward that aggregate limit; the proxy does not inspect individual encrypted response sizes. WebSockets, workers, non-proxied WebRTC, service workers, downloads, background networking and QUIC are disabled or blocked. Browsing is best effort within these restrictions.

File reservations survive worker interruption. Unattached files expire after one hour and use the existing cleanup outbox; deleting a lead queues live originals and thumbnails too. Migration 012 copies saved evidence without changing its records, restores its indexes and immutability trigger, checks all foreign keys, and restores foreign-key enforcement before returning the connection. This follows [SQLite's documented table-rebuild procedure](https://www.sqlite.org/lang_altertable.html#making_other_kinds_of_table_schema_changes). Browser controls use the documented [Playwright network APIs](https://playwright.dev/python/docs/network).

## Verification

Real Chrome tests use an exact test-only fixture host and port. That allowance is a test monkeypatch, never a production setting. They check actual requests, not just warning labels: private images, fetches, WebSockets, rebinding destinations and Chromium's usual loopback proxy bypass cannot reach the forbidden fixture. Separate checks cover private HTTP/HTTPS CONNECT, decoded response bounds, compression rejection, robots denial, supporting pages, screenshot downloads, lead cleanup and populated schema-11 upgrade/rollback.

Run all checks with `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1`. The browser tests need installed Chrome and permission to launch it. They use temporary data and fresh browser contexts, not your application records.

On 9 October 2026, **390 tests passed**. The real Arbisoft trial collected 4,412 bytes of readable text and a 792,033-byte screenshot, both labelled Live, and produced image metrics, semantic matching and an explained score. It remained partial because the local AI summary failed structured-output validation; valid outputs were retained. Trial records are isolated under `.cache/live-evidence/` and the report is `trial.json`.

The application database was backed up at `.cache/live-evidence/before-upgrade.sqlite3` and upgraded to schema 12. Exact fingerprints confirm every existing record was preserved, and foreign-key checks pass. The API and separate worker were restarted with the new code.

Update: the AI-summary failure reported above was resolved with the [summary reliability fix](phase-08-nlp.md#summary-reliability-fix-9-october-2026). Reprocessing the captured Arbisoft evidence now completes with a validated summary. The original live trial report remains historical evidence of the failure.
