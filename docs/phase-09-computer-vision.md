# Phase 9: measure the saved screenshot

Your flow is **agency → services → ICP → campaign → lead → saved evidence → job → text analysis and image measurements**.

The worker now measures a saved PNG/JPEG screenshot. It records edge density, brightness, colour distribution, dominant colour bins and the fraction of nearly flat image areas. These are observations about pixels. They do not prove that a company needs your services.

## Quick Swagger check

1. Keep the server and worker running in separate terminals using `.\scripts\start.ps1` and `.\scripts\worker.ps1`.
2. Open [Swagger](http://127.0.0.1:8000/docs). `GET /api/v1/health` should show schema **9** and worker **available**.
3. If you already have a saved-evidence job with a screenshot, use `POST /api/v1/jobs/{job_id}/retry`, body `{}`, and a new **Idempotency-Key**, such as `phase9-demo-1`. Otherwise follow the [Phase 7 upload steps](phase-07-saved-evidence.md), including its example screenshot.
4. Copy the returned `job_id` into `GET /api/v1/jobs/{job_id}`. Wait until processing finishes. The **visual_metrics** stage should succeed if the screenshot is usable.
5. Copy the `run_id` into `GET /api/v1/runs/{run_id}` and click **Execute**. In the actual **Response body**, open **visual_analysis → result → metrics** to see the measurements. **provenance** shows the evidence ID, original image hash and processing settings.

The job remains **partial**: semantic matching and scoring are the next phases. A working text model reaches `STAGE_NOT_IMPLEMENTED` at **semantic_match**. If Ollama fails, its error also remains visible, while image processing can still succeed independently.

Missing or rejected screenshots have `available: false`, a reason, and `metrics: null`. An identical retry can reuse cached measurements after verifying the original bytes. Rejecting an image makes its earlier run stale; that historical run keeps its original measurements, while a new retry respects the rejection.

## What the numbers mean

| Field | Simple meaning |
|---|---|
| `edge_density` | Fraction of pixels detected as boundaries; this is not text density |
| `brightness_mean`, `brightness_std` | Average brightness and its variation, scaled from 0 to 1 |
| `brightness_histogram` | Brightness distribution across 16 bins |
| `rgb_histograms` | Red, green and blue distributions across eight bins each |
| `dominant_colors` | Up to five most frequent coarse colour bins; centres are approximate colours |
| `low_variation_area_fraction` | Area in nearly flat 16×16 tiles; this is not guaranteed whitespace |

The original file stays unchanged. A separate working image uses EXIF orientation, a white background for transparency and proportional resizing to at most 683 pixels wide and 2,048 pixels tall. OpenCV uses fixed Canny settings (100/200, aperture 3, L2 gradient), one thread and no OpenCL. See the official [Canny documentation](https://docs.opencv.org/4.x/da/d22/tutorial_py_canny.html).

Visual scoring stays disabled: `review_score` and `calibration_id` are null, and the ICP visual weight stays zero. No calibration, quality judgement or CNN is included in this phase.

## Files and tests

| File | Purpose |
|---|---|
| `backend/app/modules/computer_vision/vision_config.py` | Fixed settings and library versions saved with every run |
| `backend/app/modules/computer_vision/vision_service.py` | Validate images, measure pixels, reuse cache and save results |
| `backend/app/modules/computer_vision/visual_analysis_schema.py` | Validate measurement and availability formats |
| `backend/app/modules/computer_vision/visual_analysis_model.py` | Immutable result linked to its run and evidence |
| `backend/app/modules/foundation/009_visual_analysis.py` | Add the result table without changing existing records |
| `backend/tests/unit/test_vision.py` | Pixel fixtures, orientation, resize, transparency and determinism |
| `backend/tests/integration/test_visual_analysis.py` | Worker, cache, history, rejection and missing-image checks |

Run `.\scripts\test.ps1` to check all phases offline. Six synthetic fixtures cover black, white, a grid, a gradient, noise and colour blocks. They verify numerical behaviour; real website reviews and human calibration remain future evaluation work.

Requirement scope: CV-01–CV-04 and CV-06, FR-14/FR-15, NFR-02 and AT-05 measurement work. Optional heuristics are deferred, CNN is module 16, and complete end-to-end acceptance still requires later modules.

Verified on 9 October 2026: **303 tests passed in 56.68 seconds**. Schema 9 preserved every existing record in the 20 previous application tables and passed foreign-key checks. Server, worker and local model readiness were available; Swagger returned HTTP 200. The saved example screenshot produced bounded measurements at 683 by 384 pixels. Its standalone measurement took approximately 0.073 seconds; this small fixture timing is not a full-workflow benchmark. No demo data was added to your real database.
