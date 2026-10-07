# 17 — Independent supervised ML experiment

**Purpose:** demonstrate honest small-data evaluation independently from rule scoring. **Requirements:** ML-01/02; SRS page 18 exploratory evaluation; NFR-07/08. **Dependencies:** 11, 14; label collection should start before scores are inspected. **Priority:** Should.

## Inputs and outputs

Inputs: permitted company feature records and independently human-assigned business-fit labels, company identity groups and labelling rubric. Outputs: reproducible logistic-regression experiment, dataset provenance, split/class balance, precision/recall/F1, limitations and optional exploratory predictions clearly separate from production. No conversion/revenue prediction.

## Future files and database changes

`experiments/ml/README.md`, `label-rubric.md`, `dataset-schema.json`, `lead_fit_experiment.ipynb`, `backend/requirements.lock.txt`; future `docs/evaluation/ml-results.md`; `backend/tests/experiments/test_group_split.py`. Use an approved local sanitized dataset; repository includes only lawful nonprivate examples. **Database changes:** none. **Endpoints:** none. Do not add the classifier to scoring service or dashboard priority.

## Implementation steps

1. Write a rubric for relevant/irrelevant business fit independent of score rules. Record annotator/date and whether the annotator saw scores; avoid treating contaminated labels as unbiased. Include incomplete cases and uncertainty rather than forcing invented certainty.
2. Record company domain group, numeric feature definitions and units, missingness, source/evidence date and independent label. Possible features: observed size, semantic cosine and raw visual metrics. Do not use final score or deterministic priority-derived label as target.
3. Separate company groups before any preprocessing so repeated campaign leads cannot leak across splits. Use a fixed seed and proposed 70/30 grouped split only when both classes and adequate groups permit it. The SRS's ten exploratory records are not sufficient evidence of a reliable trained predictor by themselves.
4. Fit missing-value imputer and scaler on training set only, then logistic regression. Do not tune/test on the evaluation split repeatedly. Record exact packages and hyperparameters.
5. Report group counts, class balance, feature coverage, confusion counts, precision, recall and F1; document zero-denominator handling. Compare a simple majority baseline, describe uncertainty and poor generalization honestly.
6. If genuine labels are too few or one class is absent, produce the reproducible notebook with explicit “accuracy unestablished”; synthetic data may test loading/splitting only. Do not publish synthetic accuracy as real predictive validity.
7. Keep all experiment outputs out of authoritative score flow and UI recommendation. Summarize limitations and data privacy/source permissions.

## Errors and recovery

Missing labels, duplicate group leakage, one-class training, too-few evaluation groups, nonfinite features and unsupported columns fail with explanatory experiment diagnostics. There is no production outage or API failure because the experiment is isolated. Remove leaked/score-derived labels and rerun only with independent data.

## Tests and acceptance criteria

Assert train/test company-group intersection empty, preprocessors fit only training data and score/priority-derived target columns are rejected. Repeated seeded split is reproducible. Report an actual independently labelled evaluation if feasible, or explicitly unestablished accuracy with functioning notebook. Confirm production scores unchanged with/without experiment artifacts. ML-01/02 completion status is reported separately from core acceptance; no commercial accuracy claim follows from this exercise.
