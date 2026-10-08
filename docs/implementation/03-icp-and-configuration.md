# 03 — ICP and scoring configuration

**Purpose:** define desired customers and preserve the exact rules used by each analysis. **Requirements:** FR-03–05; SCORE-01–04 configuration; DATA-02; SEM-03/04 input changes. **Dependencies:** 02. **Priority:** Must.

**Status:** implemented for profile/configuration storage; see [Phase 3 walkthrough](../phase-03-customer-profiles.md). Module 04 now provides actual affected-campaign counts. Affected-result counts and stale-result integration follow when modules 06/10/11 create those records. This phase provides immutable version IDs, configuration hashes, semantic-input hashes and a currentness helper.

## Inputs and outputs

Inputs: name, target description, optional canonical industries/countries/regions, size bounds, structured exclusions, desired service needs, free text preferences, weights and thresholds. Outputs: ICP with immutable version history, validated configuration, eligible component set and affected-result stale markers.

## Files and database changes

`backend/app/models/icp.py`; `backend/app/schemas/icp.py`, `scoring_config.py`; `backend/app/db/repositories/icp.py`; `backend/app/services/icp.py`, `freshness.py`, `criteria.py`; `backend/app/api/icps.py`; migration `003_icps.py`; `backend/tests/unit/test_scoring_config.py`; `backend/tests/integration/test_icp_versions.py`.

Create `icps` and `icp_versions`. Versions hold criteria, weights, thresholds, rule version and hash together. This avoids scoring with new weights but old exclusions. Target-text changes invalidate semantic results; weights-only changes invalidate scores but can reuse compatible vectors.

## Endpoints

`GET/POST /icps`, `GET/PATCH /icps/{id}`, `GET /icps/{id}/versions`. Create/edit payload is defined in shared API contracts. Archiving uses PATCH; there is no hard-delete history route. Config edit returns new version and count of affected campaigns/results.

`GET /icps/options` also supplies supported countries, explicit region sets and industry synonyms. Nested PATCH objects replace complete objects; absent members take defaults. Response configuration is under `current_version.config`. Campaign counts are implemented in module 04; result counts remain zero until result integration exists.

## Implementation steps

1. Define explicit criteria vocabulary: case-normalized exact industry labels with a small documented synonym map, ISO country codes and region-to-country sets. No LLM guesses become exclusion rules.
2. Validate nonnegative integer size bounds and min<=max. A missing bound means open-ended. Empty criteria mean not applicable, not failed fit.
3. Validate weights: finite, nonnegative, at least one applicable scored criterion and positive eligible total. Target text is required when semantic has positive weight. Non-selected criteria leave default weights stored but removed from eligible denominator.
4. Validate score bands and coverage threshold. Initialize defaults 25/20/15/40/0 and 75/50/0.6. Enabling visual contribution requires a reviewed calibration reference and explicit new weight configuration.
5. Save ICP and version transactionally; identical analytical content need not create a duplicate version, but a renamed ICP still changes entity revision. Store the full canonical JSON and hash.
6. On config changes, move current pointer, append activity and invalidate affected current recommendations. Old versions and scores remain readable. Archiving prevents selection for new analysis; reactivation restores availability.

## Errors and recovery

`422 INVALID_SIZE_RANGE`, `INVALID_WEIGHTS`, `INVALID_THRESHOLDS`, `UNKNOWN_REGION` with field details. Free text containing an exclusion request is stored as guidance only; UI explains that structured fields enforce rules. `409 VISUAL_CALIBRATION_REQUIRED` if visual weight is enabled without prerequisites. Transaction failure must not move the current-version pointer partially.

## Tests and acceptance criteria

Create UK SaaS, 20–100 employees; reject 100–20, negative size, NaN weight and zero eligible total. Verify a country preference in free text does not become a hard rule. Change weight: old version remains identical and linked scores stale. Change target text: semantic stale; change name only: analytical outputs stay current. Exclusion matches use known facts only. AT-01 verifies persistence; AT-06/07 later verify invalidation and scoring use the saved version.
