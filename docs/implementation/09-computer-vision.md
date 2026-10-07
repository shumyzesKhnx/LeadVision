# 09 — Core computer vision

**Purpose:** measure screenshots reproducibly and show what the measurements cannot prove. **Requirements:** CV-01–04, CV-06; FR-14/15; NFR-02; AT-05. CV-05 is owned by module 16. **Dependencies:** 07. **Priority:** Must measurements; optional experimental heuristic.

## Inputs and outputs

Inputs: validated usable screenshot and preprocessing configuration. Outputs: deterministic raw metrics, units/settings, unavailable reason, limitations and optional separately labelled experimental review score. Original image is preserved. Visual contribution defaults to zero in lead scoring.

## Future files and database changes

`backend/app/models/visual_analysis.py`; `backend/app/schemas/visual_analysis.py`; `backend/app/services/vision.py`, `visual_heuristic.py`; `backend/app/core/vision_config.py`; migration `009_visual_analysis.py`; `backend/tests/unit/test_visual_metrics.py`, `test_visual_unavailable.py`; future `docs/evaluation/visual-calibration.md`.

Create `visual_analyses` with screenshot FK, preprocessing/config version, raw values, usability and optional calibration ID. Review annotations affect currentness without rewriting original measurements. Cache key includes image hash and every metric/preprocessing setting.

## Endpoints

Metrics appear in `GET /runs/{id}`. Screenshot review uses module 07's `PATCH /evidence/{id}/review`. No separate direct arbitrary-image-path endpoint. Any optional heuristic is configured/versioned through ICP configuration after calibration, not enabled by a hidden environment switch.

## Implementation steps and metric definitions

1. Convert validated oriented working image to RGB; resize preserving aspect ratio to a proposed max width 683, using fixed interpolation. Keep original viewport/dimensions and record library versions.
2. Compute grayscale with documented fixed RGB-to-gray conversion. Edge density: fixed Canny thresholds 100/200, aperture 3, L2 gradient; value = nonzero edge pixels / all pixels, range 0–1. It measures edges, not text density.
3. Brightness: gray mean/255 and histogram with 16 fixed bins summing to 1; report standard deviation/255. Screen brightness does not establish text/background WCAG contrast.
4. Color distribution: fixed per-channel eight-bin RGB histograms normalized by pixel count. Optional dominant colors use deterministic quantized RGB bins and top five frequencies, without random k-means. Save bin boundaries and normalization.
5. Optional low-variation proxy: partition into 16x16 tiles, count pixel area of tiles with grayscale standard deviation <=5/255 in normalized units, divide by total included area. Document boundary tile handling. Name it low-variation-area fraction; it may include flat illustrations and is not true whitespace.
6. Persist definitions/config with results and show screenshot plus caveats. Unusable/missing images produce null metrics and reason rather than zeros.
7. If demonstrating a visual review heuristic, define versioned threshold ranges and formula in calibration document. Review at least six screenshots; record human notes and failures. Without a reviewed calibration set it remains advisory with score weight zero. Enabling a calibrated component requires explicit ICP weight changes.

## Errors and recovery

Invalid dimensions/decoder failure: CV unavailable with `INVALID_IMAGE`. Reviewer-unusable, error page or failed capture: `IMAGE_UNUSABLE`/`IMAGE_MISSING`, no opportunity value. Metric exception records stage error and preserves image/text. Unsupported configuration fails validation before measurement.

## Tests and acceptance criteria

Uniform image yields near-zero edges and concentrated brightness/color distribution; grid image yields greater edge density. Same fixture/config gives same values within defined numeric tolerance (proposed 1e-6 for normalized metrics). Resize/orientation is recorded and original hash unchanged. Unusable screenshot cannot yield a high score. Review six varied screenshots with notes. No output claims CTA recognition, text density, outdated design, usability failure or buying intent from these metrics. AT-05 includes deterministic fixtures and interpretation limits; optional heuristic absence does not fail core acceptance.
