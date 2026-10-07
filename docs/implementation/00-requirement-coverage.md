# Requirement coverage and verification

The PDF is the behavioral baseline; this matrix identifies where to implement and verify it. IDs use hyphens instead of spaces. “Owner” is a module number linked from [the index](README.md). Cross-cutting requirements are implemented in several modules and consolidated in 19. This matrix is coverage planning, not a claim of completed requirements.

## Functional requirements

| ID | PDF page | Behavior | Plan owner(s) | Acceptance evidence |
|---|---|---|---|---|
| FR-01 | 5 | Singleton persistent agency | 02 | AT-01 restart |
| FR-02 | 5 | Services and preserved approved drafts | 02, 13 | AT-01, AT-09 |
| FR-03 | 5 | Validated editable/archivable ICP | 03 | AT-01 |
| FR-04 | 5 | Evidenced hard exclusions and reasoned override | 03, 11, 14 | AT-07 exclusion fixture |
| FR-05 | 5 | Immutable configuration and stale results | 03, 04, 11 | AT-01, AT-06/07 |
| FR-06 | 6 | Campaign CRUD/archive/reactivate | 04 | AT-01 archive test |
| FR-07 | 6 | Manual leads, unknowns and user provenance | 05 | AT-02 |
| FR-08 | 6 | UTF-8 CSV limits/template/row report | 05 | AT-02 mixed rows |
| FR-09 | 6 | Domain uniqueness per campaign | 05 | AT-02 normalization/race |
| FR-10 | 6 | Search/filter/sort/detail/pagination | 05, 14, 15 | AT-02 list; UI smoke |
| FR-11 | 6 | Corrections, stale dependencies, confirmed deletion | 05, 15 | AT-02 deletion integration |
| FR-12 | 7 | Bounded website research | 07 | AT-03 limits |
| FR-13 | 7 | Cleaned traceable text and warnings | 07 | AT-03 extraction |
| FR-14 | 7 | Fixed viewport screenshot, thumbnail, review | 07, 15 | AT-03 capture/review |
| FR-15 | 7 | Labelled saved evidence and image validation | 07 | AT-03 offline/import |
| FR-16 | 7 | Public destinations only, redirects/subrequests | 07 | AT-03 egress/rebinding |
| FR-17 | 8 | Bounded source-preserving preprocessing | 08 | AT-04 truncation |
| FR-18 | 8 | Supported structured summary and hypotheses | 08 | AT-04 CloudBooks |
| FR-19 | 8 | Strict model schema and bounded repair | 08, 13 | AT-04 invalid output |
| FR-20 | 8 | Distinct sources and correction precedence | 05, 08, 11, 13 | AT-04 unknown size |
| FR-21 | 8 | Free local runtime, bounds/cache/disconnection | 01, 06, 08 | AT-04/11/12 |

## Analysis and outreach requirements

| ID | PDF page | Behavior | Plan owner(s) | Acceptance evidence |
|---|---|---|---|---|
| CV-01 | 9 | Validated consistent image preprocessing | 09 | AT-05 original preserved |
| CV-02 | 9 | Defined reproducible OpenCV metrics | 09 | AT-05 uniform/grid |
| CV-03 | 9 | No unsupported visual claims | 09, 13, 16 | AT-05 human notes |
| CV-04 | 9 | Optional versioned advisory heuristic, zero default weight | 03, 09, 11 | AT-05/07 calibration guard |
| CV-05 | 9 | Should ResNet18 features/reference comparison | 16 | Supplementary AT-05 |
| CV-06 | 9 | Missing/unusable image stays missing | 07, 09, 11 | AT-05 unavailable |
| SEM-01 | 10 | Same-model cached text vectors | 10 | AT-06 cache/config |
| SEM-02 | 10 | Raw cosine and clipped normalized value | 10 | AT-06 arithmetic |
| SEM-03 | 10 | Semantic separate from structured rules | 10, 11 | AT-07 exclusion |
| SEM-04 | 10 | Missing similarity and input/model freshness | 03, 10 | AT-06 staleness |
| SEM-05 | 10 | Small local NumPy search and eligibility filter | 10, 12 | AT-08 version/agency |
| SCORE-01 | 11 | Backend components/weights/source breakdown | 11 | AT-07 arithmetic |
| SCORE-02 | 11 | Available-weight average and coverage | 11 | AT-07 90.59/.85 |
| SCORE-03 | 11 | Bands, completeness/currentness/exclusion gate | 11, 14 | AT-07 boundary/manual |
| SCORE-04 | 11 | Preserved history and separate reasoned overrides | 11 | AT-07 history |
| RAG-01 | 12 | Pasted/TXT approved agency knowledge | 12 | AT-08 limits |
| RAG-02 | 12 | Bounded chunks, vectors and current-version index | 12 | AT-08 edited versions |
| RAG-03 | 12 | Up to three relevant sources saved with draft | 12, 13 | AT-08 retrieval |
| RAG-04 | 12 | Supported claims and service-only fallback | 12, 13 | AT-08 empty; draft review |
| OUT-01 | 12 | Grounded concise subject/message | 13 | AT-09; five-draft review |
| OUT-02 | 12 | Draft/Edited/Approved/Rejected versions and review | 13 | AT-09 history/races |
| OUT-03 | 12 | Approved manual use, no sending | 13, 15 | AT-09 copy/no contact change |

## Pipeline and supplementary requirements

| ID | PDF page | Behavior | Plan owner(s) | Acceptance evidence |
|---|---|---|---|---|
| PIPE-01 | 13 | Explicit transitions and terminal reopening reason | 14 | AT-10 transitions |
| PIPE-02 | 13 | Time/origin history without retry duplication | 01, 05, 06, 11, 13, 14 | AT-10 activity |
| AN-01 | 13 | Filtered database dashboard counts | 14 | AT-10 exact counts |
| EXP-01 | 13 | Should formula-safe lead CSV | 14 | Optional export safety |
| AUTO-01 | 13 | Should bounded local n8n/idempotency | 18 | Actual supplementary workflow |
| ML-01 | 13 | Should independent logistic regression evaluation | 17 | Label/split/metrics report |
| ML-02 | 13 | No score-derived ground truth or synthetic validity | 17 | Data provenance audit |

Tags are a Should feature on page 3, covered optionally in 14. A follow-up draft and richer charts are May features on page 3, deliberately deferred; implementing ordinary new draft series does not claim a follow-up feature. Visual reference similarity is handled only in the supplementary CNN plan. Future enterprise features are outside all plans.

## Data, interface and nonfunctional requirements

| ID | PDF page | Behavior | Plan owner(s) | Acceptance evidence |
|---|---|---|---|---|
| DATA-01 | 14 | SQLAlchemy/SQLite FKs and stage transactions | 01, 06, all persistence modules | AT-01/11 transaction tests |
| DATA-02 | 14 | Provenance, UTC/local display, full freshness links | 03, 05–15 | AT-04/06/07/09 |
| DATA-03 | 14 | Local retention and consistent restored backup | 01, 05, 07, 19 | AT-12 screenshots after restore |
| API-01 | 15 | Complete backend-first documented REST | 01–14 | Swagger core walkthrough |
| API-02 | 15 | Immediate jobs, persistent single worker, key reuse | 06 | AT-11 concurrency |
| API-03 | 15 | Restart interruption and bounded retry/history | 06, 08 | AT-11 kill/restart |
| API-04 | 15 | Safe consistent field/stage errors | 01 and all route modules | AT-04/11 redaction |
| UI-01 | 15 | Same-origin plain HTML/CSS/JS required views | 15 | Complete browser walkthrough |
| UI-02 | 15 | Accessible forms/states and safe rendering | 15 | Keyboard/XSS/error smoke |
| NFR-01 | 16 | Free core operation and licences/downloads | 01, 08, 10, 19 | AT-12 manifest |
| NFR-02 | 16 | CPU, serialized capture/inference, <14 GB target | 06–10, 16, 19 | AT-12 measured system peak |
| NFR-03 | 16 | CRUD <1s/100 leads, warmed analysis <5min target | 06, 19 | AT-11/12 timing report |
| NFR-04 | 16 | Model <=5 GB/data <2 GB reference targets | 01, 07, 19 | AT-12 measured bytes |
| NFR-05 | 16 | Offline saved demo after initial setup | 07–13, 19 | AT-12 disconnected run |
| NFR-06 | 16 | Reviewable partial/stale results and recovery | 06, 11, 15, 19 | AT-06/11 |
| NFR-07 | 16 | Responsibility separation, config and tested pins | 01, all modules | Structure/dependency audit |
| NFR-08 | 16 | Reproducible setup/demo/backend/tests/limitations | 01, 19 | AT-12 fresh setup |

Page 16 security statements have no separate SRS IDs: loopback/secret handling and Host/Origin guards -> 01; untrusted input and parameterized DB -> all service modules; safe files -> 01/05/07/12; prompt injection/no tool authority -> 08/13; no sending -> 13/18. Page 17 technology roles are allocated in the shared design; LangChain is confined to RAG, NumPy to small retrieval, optional scikit-learn to 17, and Git/GitHub to delivery.

## Acceptance test owners

| Test | Core owner(s) | Planned evidence |
|---|---|---|
| AT-01 | 02–04, 19 | Create agency/services/ICP/campaign, restart and compare |
| AT-02 | 05 | Mixed import, identity, correction and deletion |
| AT-03 | 07 | Public fixture, forbidden egress and offline saved evidence |
| AT-04 | 08 | Source summary, unknown employees and invalid JSON |
| AT-05 | 09; 16 supplementary | Deterministic metrics, blocked image, bounded interpretations |
| AT-06 | 10 | Comparable vectors, missing input and invalidation |
| AT-07 | 11 | Exact worked arithmetic, sparse coverage and eligibility |
| AT-08 | 12, 13 | Eligible retrieval versions and no invented fallback claims |
| AT-09 | 13 | Reviewed immutable draft history and no sending |
| AT-10 | 14 | Manual events and exact campaign-filtered counts |
| AT-11 | 06 | Idempotency, interruption, retry and responsive CRUD |
| AT-12 | 19 | Offline end-to-end demo, resources and restore |

UC-01 is integrated by 05–15; UC-02 import by 05; UC-03 cached demo by 07/19; UC-04 runtime failure by 06/08/15; UC-05 empty retrieval by 12/13. O1 evidence summarization maps to 07/08, O2 explanation to 10/11, O3 technology demonstrations to 08–13/16–18, O4 human control to 05/13/14, and O5 reproducibility to 19. Page 19 gates and submission dates are scheduled in the index.
