# 16 — CNN feature demonstration

**Purpose:** demonstrate pretrained deep-learning features without pretending they measure website quality. **Requirements:** CV-05 and CV-03/04 interpretation limits; NFR-01/02/04; supplementary AT-05 evidence. **Dependencies:** 09, 15. **Priority:** Should. No core dependency uses this output.

## Inputs and outputs

Inputs: usable screenshots, lawful curated reference gallery, fixed ResNet18 weights/digest and preprocessing. Outputs: feature vector, nearest references/cosine similarities, preprocessing metadata and explicit experimental limitations. No CNN training, detector or quality classifier is planned.

## Future files and database changes

`backend/app/models/cnn_feature.py`; `backend/app/services/cnn_features.py`; `backend/app/integrations/resnet_features.py`; `backend/app/api/visual_references.py`; migration `016_cnn_features.py`; `experiments/cnn/reference-manifest.json`, `README.md`; `backend/tests/unit/test_cnn_similarity.py`; future `docs/evaluation/cnn-results.md`.

Create optional `cnn_features` with visual-analysis FK, weights/preprocessing and vector. Reference manifest stores image ID/hash, permission/source, preprocessing and human notes; store small legal fixtures in repo, large reference screenshots outside it. No score-table changes and no nonzero visual weight from CNN alone.

## Endpoints

Optional `GET /runs/{id}/visual-reference-comparison` displays already computed result. A local experiment command can populate comparisons; do not introduce unrestricted model-loading HTTP commands. If integrated into jobs, optional CNN stage absence/failure never makes a completed core run fail.

## Implementation steps

1. Verify weight/source terms and collect a small proposed 6–10-image lawful gallery with varied layouts. Attractive-reference labels are human notes, not ground-truth sales outcomes.
2. Load ResNet18 in eval/inference mode; use the selected weight's official transform. Record resize/crop/mean/std, library versions and weight digest. Extract pooled features before classifier (expected 512 dimensions; assert against installed implementation).
3. Cache reference/lead vectors by image+weight+transform hash. Use cosine and deterministic ties; zero/invalid vectors produce unavailable result.
4. Execute sequentially under resource limits and unload CNN when needed before generation. Measure actual memory/download bytes; do not promise hardware fit from parameter count.
5. Show nearest examples and interpretation text: generic ImageNet representations compare appearance, not usability, business fit or buying intent.
6. Record six reviewed screenshot cases and where neighbors are misleading. Keep quantitative comparison separate from authoritative lead score.

## Errors and recovery

Missing optional weights: explicit unavailable/deferred result, never surprise download during offline demo. Invalid/unusable image: skip. Memory pressure: unload and record limitation; core CV/text workflow stays usable. Bad reference licence/source means exclude the reference.

## Tests and acceptance criteria

Fake-vector unit tests verify cosine/ties; pinned-weight fixture inference confirms finite expected dimensions and stable repeated values within tolerance. Show at least one reference comparison with configuration and limitations. Report timing/memory and misleading examples. Acceptance is a demonstrable inference feature, not predictive accuracy. If deferred, say CV-05 incomplete and retain Must CV-01–04/06 evidence. Upgrade to Must only through recorded instructor scope amendment.
