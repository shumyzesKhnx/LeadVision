# Phase 11: explained company scores

The system now combines the information from previous phases into a company fit score. The flow is:

**Agency/services → ICP → campaign → lead → saved evidence → analysis → explained score.**

Your ICP describes the customers you want. The score compares each lead with that profile. It is a rule-based comparison, not a prediction that the company will buy your services.

## What the result means

| Field | Simple meaning |
|---|---|
| `score` | Fit from 0 to 100, using the information available. `null` means nothing could be scored. |
| `coverage` | How much of the selected information was available: `0.6` means 60%. |
| `score_band` | High, Medium or Low from the saved ICP thresholds. |
| `priority` | The band, or Needs review when information is insufficient or the result is stale. |
| `ineligible` | A known fact matches an ICP exclusion. This remains visible even with a high score. |
| `is_current` | Whether the result still matches the lead, profile and processing inputs. |
| `recommended_for_qualification` | Current High fit with sufficient coverage and no exclusion. It does not change the lead's pipeline state. |
| `components` | Each input, weight, contribution and explanation. |

Industry, country and employee count use the details you entered or corrected. Generated guesses are not automatically accepted as facts. Semantic matching contributes the text similarity from Phase 10. Image measurements remain visible, but visual scoring has weight zero until a reviewed calibration exists.

A missing employee count is different from a known count outside your desired range. Missing information reduces coverage; a known mismatch contributes zero fit and still counts as available information.

The default weights are industry 25, geography 20, size 15 and semantic 40. Only applicable criteria count. Score = weighted total / available weight. Coverage = available weight / applicable weight. For example, industry 100, geography 100, missing size and semantic 80 give **90.59 fit with 85% coverage**. Custom ICP thresholds apply to their own saved version.

## Quick Swagger check

Open [Swagger](http://127.0.0.1:8000/docs). The API and separate worker must both be running.

1. Execute `GET /api/v1/leads`. Copy your lead ID and latest job ID from the response body.
2. If that lead already has an analysis, execute `POST /api/v1/jobs/{job_id}/retry`. Enter the job ID, a new `Idempotency-Key` such as `arbisoft-score-1`, and `{}` as the body. This creates a new run and reuses its saved evidence. Completed jobs can also be recomputed. For a lead with no analysis, follow the [saved-evidence upload steps](phase-07-saved-evidence.md) first.
3. Poll `GET /api/v1/jobs/{job_id}` using the **new** job ID until processing finishes.
4. Execute `GET /api/v1/leads/{lead_id}`. Look under **Response body** for `score`, `coverage`, `priority`, `ineligible` and `score_detail`.
5. Execute `GET /api/v1/leads/{lead_id}/scores` to see history. Use a returned score ID with `GET /api/v1/scores/{score_id}` for the full explanation. `GET /api/v1/runs/{run_id}` also includes `score_result` alongside NLP, image and semantic results.

Paste IDs without surrounding quotes or commas. A null score or Needs review result can be correct when inputs are missing; check its components and warnings. A completed job means its processing finished, not that the company is a good fit. A partial job can still contain a supported score if another analysis component failed.

Correcting industry, country, employee count, description or other analytical inputs makes earlier scores stale. Changing analytical ICP settings also creates a new version. Recompute to obtain a current score; the original calculation remains in history. Contact-only edits do not invalidate analytical results.

## Optional reviewer decisions

`POST /api/v1/leads/{lead_id}/overrides` records a human decision beside the calculation. Supply `If-Match` with the lead's current revision, such as `"2"`, and use the latest score ID:

```json
{
  "score_id": "PASTE-SCORE-ID-HERE",
  "kind": "priority",
  "value": "Low",
  "reason": "Reviewed manually; this company is not a current outreach target.",
  "reviewer": "Agency owner"
}
```

Priority values are `High`, `Medium`, `Low`, `Needs review` and `clear`. Exclusion/qualification decisions use `allow` or `clear`. Clearing appends history; it does not erase earlier decisions. Relevant input changes deactivate the old decision. Priority and exclusion decisions require a current score; an explicit qualification acknowledgement may reference the latest stale score, but pipeline qualification is implemented later in Phase 14.

These decisions never rewrite the computed score, coverage, exclusion flag or recommendation. Reviewer names are labels entered by the operator, not authenticated identities.

## Files added

| Folder/files | Purpose |
|---|---|
| `backend/app/modules/scoring/scoring_service.py`, `eligibility.py`, `overrides.py` | Calculate fit, check exclusions and record reviewer decisions. |
| `backend/app/modules/scoring/score_model.py`, `reviewer_override.py` | Store scores, individual components and decision history. |
| `backend/app/modules/foundation/011_scores.py` | Add the three tables without changing existing records. |
| `backend/app/modules/scoring/scores_repository.py` | Read the latest score and older results. |
| `backend/app/modules/scoring/score_schema.py` | Validate decision inputs and define score responses. |
| `backend/app/modules/scoring/scores_api.py`, `overrides.py` | Expose the new Swagger endpoints. |
| `backend/tests/unit/test_score_arithmetic.py`, `integration/test_score_history.py` | Check arithmetic, missing inputs, exclusions, history, overrides and rollback. |

Existing lead lists now expose scores and support filtering by current computed priority and sorting by score. Missing scores appear last in both score sort directions. The worker saves score/components/activity together in one transaction.

## Verification and next work

On 9 October 2026, **350 tests passed**. Checks cover arithmetic boundaries, custom thresholds, missing inputs, hard exclusions, stale history, decision clearing, deletion, score sorting/pagination, recomputing completed jobs and rollback after a scoring save failure. Your application database was backed up at `.cache/phase-11/before-upgrade.sqlite3`; every existing table retained its exact records during migration to schema 11. Trial data uses isolated databases under `.cache/phase-11/`, not your real leads.

A real local-model trial produced **90.19 fit, 100% coverage and High priority**, retained pipeline state New and reused embedding caches on repeat. That trial remained partial because the local generation model returned an invalid structured summary; the validator rejected it, while entered company facts and valid semantic matching still produced the score. Broader NLP quality evaluation remains pending. The isolated report is `.cache/phase-11/real-trial.json`.

Live website collection in module 07 is now implemented; see the [live walkthrough](phase-07-live-websites.md). Next is Phase 12 knowledge/retrieval, Phase 13 outreach drafts and Phase 14 pipeline/dashboard. Phase 15 adds the browser interface. Saved-evidence analysis through scoring now works; automatic company discovery remains outside the current scope.
