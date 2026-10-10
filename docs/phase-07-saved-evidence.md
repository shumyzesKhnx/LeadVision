# Phase 7: saved website evidence

You can now give a lead a saved website text file and a screenshot. The worker reads this evidence, records where it came from, and keeps it with that attempt. This is the **saved-evidence milestone** of phase 7. Live website fetching remains at the later milestone in our implementation sequence.

Your flow is **agency → services → ICP → campaign → lead → upload evidence → analysis job → view evidence**. NLP, computer vision and scoring come next.

## Quick Swagger check

Keep the API and worker running. Open [Swagger](http://127.0.0.1:8000/docs); health should report schema version 7 and worker available. On a later day, start `.\scripts\start.ps1` and `.\scripts\worker.ps1` in separate terminals.

1. Use a test lead called **Saved Evidence Demo**, with website `https://saved-demo.example.com` and your existing campaign ID. Create it through `POST /api/v1/leads`, then copy its returned `id`.
2. Open `POST /api/v1/leads/{lead_id}/saved-evidence` and select **Try it out**. Paste the lead ID.
3. For **text_file**, select [the example text](examples/phase-07-saved-website.txt). For **image_file**, select [the example screenshot](examples/phase-07-saved-screenshot.png). Both are clearly labelled fictional test fixtures.
4. Keep **source_mode** as `uploaded`. Leave **original_url**, **collected_at** and **title** empty, and disable **Send empty value** for optional fields if Swagger shows it. Execute.
5. The `201` response says which files are available. Copy its `upload_token`.
6. Open `POST /api/v1/leads/{lead_id}/analysis-jobs`, use the same lead ID, and enter **Idempotency-Key** `saved-demo-1`. Paste this body, replacing the token:

```json
{
  "mode": "uploaded",
  "upload_token": "PASTE_UPLOAD_TOKEN_HERE",
  "include_supporting_pages": false
}
```

7. Copy `job_id` into `GET /api/v1/jobs/{job_id}`. Text/image acquisition should finish. The job becomes **partial**, with `STAGE_NOT_IMPLEMENTED` at **preprocess_text**, because NLP is the next phase.
8. Copy `run_id` into `GET /api/v1/runs/{run_id}/evidence`. It lists the text and image, their hashes, dimensions and source labels. The image's `image_url` and `thumbnail_url` can be opened at `http://127.0.0.1:8000` followed by that path.

For your own saved evidence, copy visible website text into a UTF-8 `.txt` file and save a PNG/JPEG screenshot. You may provide its original public URL and a genuine collection timestamp with timezone, such as `2026-10-08T12:00:00+05:00`. Leave an unknown time blank; import time is recorded separately. This upload does not visit the URL.

## Rules explained simply

- Text: at most **1 MB**, valid UTF-8, nonblank. The original is kept; the worker uses at most **30,000 characters** and reports truncation.
- Image: static **PNG/JPEG**, at most **10 MB** and **20 million pixels**. The original stays unchanged. Its thumbnail applies EXIF orientation and fits inside 400×300 pixels.
- Text only or image only is allowed. A malformed image is discarded with a warning when valid text is available. Oversized uploads are rejected. Missing or changed screenshot files produce warnings and keep usable text.
- Source labels are **Uploaded** or **Cached**, according to your selection. Upload and job modes must match. No saved evidence is labelled Live, and no viewport/browser capture information is invented.
- An unattached token expires after **one hour**. The worker removes expired files. One token attaches to one job; repeating the same request/key returns that job.
- Retry a partial/failed/cancelled job with a new request key and body `{}` to reuse its attached evidence. A new upload token can replace that evidence. Retries preserve an existing unusable review when reusing its upload.
- `PATCH /api/v1/evidence/{evidence_id}/review` accepts `{"usable": false, "reason": "Screenshot shows a blocking overlay"}` with **If-Match** set to the quoted evidence revision, for example `"1"`. Reviews keep the original files and mark affected run inputs stale. Re-enable with `{"usable": true}` and the latest revision.
- Deleting a lead still needs confirmation and its current revision. Active jobs block deletion. With evidence files, deletion returns **202**, while the worker finishes durable file cleanup; without files it returns **204**.

## What the files do

| File/folder | Purpose |
|---|---|
| `backend/app/modules/evidence/evidence_api.py` | Upload, view evidence and review usability |
| `backend/app/modules/evidence/artifacts_api.py` | Safely return owned original images and thumbnails |
| `backend/app/modules/evidence/evidence_service.py` | Save manifests, attach tokens, run acquisition stages and clean files |
| `backend/app/modules/evidence/text_extraction_service.py` | Validate and bound saved readable text |
| `backend/app/modules/evidence/image_validation_service.py` | Validate images and create thumbnails |
| `backend/app/modules/evidence/evidence_model.py` | Upload ownership, provenance and review records |
| `backend/app/modules/evidence/evidence_schema.py` | Validate metadata/reviews and define responses |
| `backend/app/modules/foundation/007_evidence.py` | Add evidence tables and immutable-source constraints |
| `backend/tests/unit/test_images.py` | File limits, image formats, orientation, animation and pixel safety |
| `backend/tests/integration/test_saved_evidence.py` | Upload, restart, token rules, review, integrity and cleanup checks |
| `backend/tests/integration/test_evidence_migration.py` | Existing-data preservation and failed-upgrade rollback |

Pillow is pinned in the dependency lock for validation and thumbnails. Image handling follows its [official image-opening and decompression-safety documentation](https://pillow.readthedocs.io/en/stable/reference/Image.html). No new AI model or browser installation is needed for this milestone.

Run `.\scripts\test.ps1` to check all completed modules using temporary data. Full AT-03 acceptance remains pending the live HTTP/browser work, including DNS, redirects and browser subrequest safety. Next is **phase 8: NLP and the local model runtime**, using this saved evidence.

Verified on 8 October 2026: **261 tests passed in 26.86 seconds**. Migration 007 preserved every existing application record, including your two leads. Swagger returned HTTP 200, all five evidence/artifact routes appeared, and the API/worker are running on version 0.7.0 with schema 7. No demonstration uploads or jobs were added to your real database during verification.
