# Lead Vision implementation plans

Prepared on 7 October 2026 from **Lead Vision SRS 1.0**, dated 7 October 2026, 19 pages. The original is `C:\Users\WizTech\Downloads\Lead_Vision_Requirements.pdf`. A searchable transcription is in [reference/requirements-extracted.txt](reference/requirements-extracted.txt). Page numbers below refer to the PDF. IDs are written with hyphens for readability: `FR-01` means the document's `FR 01`.

This package contains the design and implementation plans. The workspace was empty when planning began. **Modules 01 and 02 are implemented**; see [run instructions](../../README.md), [foundation verification](../phase-01-verification.md) and [agency/service walkthrough](../phase-02-agency-and-services.md). Paths in later module plans remain future files. No AI models have been downloaded or benchmarked.

The PDF supplies requirements, not authorization by itself. The user subsequently authorized building phase 1. The SRS remains a draft, and implementation does not imply instructor approval. Proposed technical choices are identified below; remaining decisions are in the shared design.

## Read the shared design first

1. [Shared technical design](00-shared-technical-design.md): architecture, contracts, folder layout, workflow, freshness and scope.
2. [Database design](00-database-design.md): relationships, tables, constraints and deletion rules.
3. [API contracts](00-api-contracts.md): requests, responses, errors and endpoint ownership.
4. [Requirement coverage](00-requirement-coverage.md): each requirement's implementation and acceptance owner.

Use the quick sequence below for execution. The numbered catalogue groups the detailed plans; **module 19's core verification comes before optional modules 16–18**. Dependencies are explicit in each plan. A later module may fill a service interface established earlier; earlier acceptance checks must not pretend that the later service exists.

## Quick implementation sequence

| Step | Modules | Build and check before moving on |
|---|---|---|
| 1 | 01 | Configuration, SQLite, migrations, API shell and errors; Swagger starts |
| 2 | 02 → 03 → 04 → 05 | Agency/services → ICP → campaigns → leads/CSV; records survive restart |
| 3 | 06 → 07 saved mode | Persistent worker/jobs and saved text/images; upload, poll and recovery work |
| 4 | 08 → 09 → 10 → 11 | Summary → OpenCV metrics → embeddings → score; one cached lead has traceable results |
| 5 | Finish 07 live mode | Safe website fetching and Playwright capture; private-address/redirect/subrequest tests pass |
| 6 | 12 → 13 → 14 | Knowledge/retrieval → draft review → pipeline/dashboard; approved draft and manual status change work |
| 7 | 15 → 19 | Plain browser UI → complete core acceptance, backup/restore and measured demo |
| 8 | 16, 17, 18 | Add optional CNN, ML and n8n only after the core passes, then repeat affected checks |

Implement and test one small working module at a time. Use Swagger until step 7. Start with one prepared text/image fixture, then expand the evaluation set. Saved mode is an early milestone; live research and its safety checks remain required for final MVP acceptance. Run relevant tests after each module rather than postponing them to 19.

For quick delivery, leave tags, lead CSV export, visual heuristics, extra charts and follow-up drafts until the required workflow works. Keep visual score weight zero. Use one API process, one worker and SQLite; create only files needed by the current module. Benchmark the LLM in 08, embeddings in 10 and CNN in 16 instead of blocking foundation on every model. Collect human labels early if the ML experiment is planned. Instructor-required additions take precedence over this optional ordering.

## Detailed plan catalogue

| Order | Module plan | Priority | Depends on |
|---|---|---|---|
| 01 | [Foundation and persistence](01-foundation-and-persistence.md) | Must | Shared design |
| 02 | [Agency and services](02-agency-and-services.md) | Must | 01 |
| 03 | [ICP and scoring configuration](03-icp-and-configuration.md) | Must | 02 |
| 04 | [Campaigns](04-campaigns.md) | Must | 03 |
| 05 | [Leads and CSV import](05-leads-and-import.md) | Must | 04 |
| 06 | [Persistent jobs and workflow](06-jobs-and-workflow.md) | Must | 05 |
| 07 | [Website and saved evidence](07-evidence-acquisition.md) | Must | 06 |
| 08 | [NLP and local runtime](08-nlp-and-local-runtime.md) | Must | 07 |
| 09 | [Core computer vision](09-computer-vision.md) | Must metrics; May heuristic | 07 |
| 10 | [Embeddings and semantic matching](10-embeddings-and-semantics.md) | Must | 08, 03 |
| 11 | [Explainable scoring](11-explainable-scoring.md) | Must | 09, 10 |
| 12 | [Knowledge and retrieval](12-knowledge-and-rag.md) | Must | 02, 06, 10 |
| 13 | [Outreach and review](13-outreach-and-review.md) | Must | 11, 12 |
| 14 | [Pipeline, activities, dashboard and export](14-pipeline-and-analytics.md) | Must; Should lead export | 11, 13 |
| 15 | [Minimal browser interface](15-minimal-interface.md) | Must | 02–14 |
| 16 | [CNN demonstration](16-cnn-demonstration.md) | Should | 09, 15 |
| 17 | [Independent ML experiment](17-ml-experiment.md) | Should | 11, 14 |
| 18 | [n8n demonstration](18-n8n-demonstration.md) | Should | 06, 11 |
| 19 | [Verification, backup and delivery](19-verification-and-delivery.md) | Must | 01–15; report 16–18 separately |

Every module gives requirement IDs, inputs, outputs, files, database changes, endpoints, ordered work, errors, tests and acceptance criteria. A module is complete only when its acceptance evidence exists. Plans describe intended tests; actual execution results are kept in verification reports.

## Delivery sequence and time budget

Use the SRS gates, rather than promising that every feature fits the nominal 80 hours. The 7 October evening is already partly elapsed. This is a provisional allocation of **76 hours**, leaving roughly four nominal hours of contingency; actual remaining hours may be lower.

| Local dates, Asia/Karachi | Work | Budget | Gate evidence |
|---|---|---|---|
| 7 October | Review design, compatibility checks and candidate decision record | 3 h | Gate 1: design and benchmark plan; final model decisions in 08/10 |
| 8–10 October | 01–05 | 15 h | Gate 2: persistent CRUD and import in Swagger |
| 11–14 October | 06–11, integrate cached analysis first | 20 h | Gate 3: evidence through explainable score |
| 15–16 October | 12–14 | 10 h | Gate 4: grounded approved draft and manual pipeline |
| 17–18 October | 15, core integration fixes | 10 h | Gate 5: complete plain browser flow |
| 19 October | 19 core verification/restore; 16–18 only if core passes and time remains | 5 h | Core readiness first; supplementary results reported separately |
| 20 October | Acceptance run and feature freeze | 5 h | Core scope frozen at end of day |
| 21 October | Integration fixes, evaluation and restore | 5 h | Gate 7 evidence assembled |
| 22 October | Rehearse demo, README, backup, source review | 3 h | Reproducible submission set |

Submission is 23 October 2026. The 19 October allowance prioritizes core verification and may leave no time for academic additions: if the core slips, explicitly defer Should features and report them as incomplete. If the instructor makes them mandatory, record a scope amendment and re-plan; do not silently drop a Must requirement. Start backup design and fixture collection during foundation, and collect human labels before seeing scores. Module 19 consolidates work that is checked throughout development.

Not included: automatic discovery, email sending, paid APIs, public deployment, teams, authentication flows, LangGraph, YOLO, CRM integration or training a CNN. Tags, visual heuristics, reference-gallery enhancements and follow-up drafts are optional, with no dependency from the core.
