# 11 — Explainable scoring

**Purpose:** calculate one transparent score while keeping completeness, eligibility and human decisions separate. **Requirements:** SCORE-01–04; FR-04/05/20; SEM-02–04; CV-04/06; DATA-02; AT-07. **Dependencies:** 09, 10. **Priority:** Must.

## Inputs and outputs

Inputs: immutable ICP/rule/threshold version, reviewed industry, known country and employee count, semantic result, optional calibrated visual result, provenance and freshness. Outputs: score or null, component breakdown, coverage, numerical band, displayed priority, hard-exclusion reasons, qualification recommendation, independent reviewer override history.

## Implementation files and database changes

`backend/app/modules/scoring/score_model.py`, `reviewer_override.py`; `backend/app/modules/scoring/score_schema.py`; `backend/app/modules/scoring/scoring_service.py`, `eligibility.py`, `overrides.py`; `backend/app/modules/scoring/scores_repository.py`; `backend/app/modules/scoring/scores_api.py`, `overrides.py`; migration `011_scores.py`; `backend/tests/unit/test_score_arithmetic.py`, `test_score_missing.py`, `test_exclusions.py`; `backend/tests/integration/test_score_history.py`.

Create `score_runs`, `score_components`, `reviewer_overrides`. Store source snapshots and exact input/rule/config references, not just total. Calculated scores are append-only. Latest result query never erases older score history.

## Endpoints

`GET /leads/{id}/scores`; `GET /scores/{id}`; `POST /leads/{id}/overrides`. Recompute through a new analysis job; no PATCH of score totals. Override requires kind/value/reason/reviewer and applicable score ID. Override is displayed beside the score; it never changes arithmetic.

## Implementation steps

1. Resolve component availability separately from value. Industry is 100/0 only for reviewed target/mismatch; geographic fit is 100/0 for known country in/out of target set; size is 100/0 inside/outside configured inclusive bounds. Unknown is missing, not 0. Unselected criterion is not applicable. Semantic is normalized clipped cosine; visual is absent by default.
2. Evaluate hard exclusions using evidenced/user-reviewed structured fields only. Unknown industry/country does not count as exclusion, and free text cannot trigger one. Record matching fact and rule. Exclusion flag remains visible even if an operator override is later granted.
3. Let E = sum of weights for applicable components, A = sum for available components, N = sum(weight*value). If E<=0 reject invalid config. If A=0, score=null and coverage=0. Otherwise score=N/A, coverage=A/E. A known value of 0 still counts as available evidence. Applicable zero-weight components do not change denominators.
4. Store numerator contribution `weight*value` and normalized contribution `(weight/A)*value`; contributions sum to total. Do not round before calculation. UI shows score one decimal and coverage percent.
5. Read band and coverage thresholds from the saved ICP configuration, never hardcode defaults into evaluation. With defaults: >=75 High, >=50 Medium, else Low. Display Needs review if no score, coverage below the configured minimum (default 0.6) or results stale. Keep numerical band for explanation where calculable. Hard exclusion is an independent Ineligible badge; high arithmetic does not override it.
6. Recommend qualification only with numerical High, coverage meeting the saved minimum, no active hard exclusion and current results. Recorded exclusion override may permit an explicit manual decision, but cannot silently become model/rule eligibility. Module 14 enforces manual qualification reasons.
7. Save stage transactionally, invalidate list/dashboard caches if any, record one scoring activity and finalize the integrated analysis workflow. Failed semantic/CV still permits a structured partial score.

## Errors and recovery

Invalid weights/config fail `SCORING_CONFIG_INVALID`; absent components produce a valid unavailable result. Incompatible semantic vectors make that component missing. CV unavailable never becomes high opportunity. A scoring persistence failure rolls back score/components/activity together without deleting evidence. Stale outputs remain visible with recompute action.

## Tests and acceptance criteria

- Industry 100, geography 100, missing size, semantic 80: N=7,700; A=85; score=90.588235...; coverage=.85; UI 90.6 High.
- Only industry: score=100, coverage=.25, Needs review, no recommendation.
- All missing: null score, zero coverage. Known mismatch 0 still contributes coverage. Unselected size removes its weight from E. Zero-weight visual never inflates coverage.
- Test exact boundaries 49.999/50/74.999/75 and coverage .5999/.6; preserve precision.
- Save custom bands 80/55 and minimum coverage .8; verify those values govern the new score while the old default-version result remains unchanged.
- Explicit excluded country with high semantic fit stays Ineligible. Unsupported model size/industry is not silently scored.
- Weight/input changes preserve old score/version and suppress current recommendation. Override reason is required and original score unchanged.

AT-07 passes with these fixture calculations and history. Production score must never depend on ML extension output.

## Implemented status, 9 October 2026

Core scoring is implemented in schema 11. Tests for missing values and exclusions are grouped into `test_score_arithmetic.py` and `test_score_history.py` rather than additional small test files. Lead detail/list and analysis-run responses expose calculated scores; priority filtering happens before pagination. Five component rows retain availability and contributions even when a component is disabled. Score rows, component rows and reviewer history reject database updates. Clearing a decision appends a new `clear` record.

Generated industry/employee guesses need operator review through lead corrections before scoring. User-entered facts are explicit but not independently verified. Visual calibration remains unimplemented and visual weight remains zero. No pipeline transitions are automatic. Qualification decision records are groundwork for module 14. Recompute through a fresh analysis job, including retry of a completed job; saved score history remains visible and older scores are marked superseded.

See [actual verification and Swagger instructions](../phase-11-explained-scoring.md).
