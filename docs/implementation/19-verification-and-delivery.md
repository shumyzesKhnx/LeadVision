# 19 — Verification, backup and delivery

**Purpose:** prove the complete saved-evidence workflow, report measured limits and make restoration reproducible. **Requirements:** DATA-03; NFR-01–08; AT-01–12; O1–O5; SRS pages 18–19 gates, GitHub and definition of done. **Dependencies:** 01–15; record 16–18 supplementary status honestly. **Priority:** Must.

## Inputs and outputs

Inputs: implemented core modules, curated legal fixtures, independent human review, benchmark-selected model manifest and actual laptop measurements. Outputs: acceptance report, evaluation findings, consistent backup/restore commands, README/demo instructions, pinned dependencies, repository exclusion audit and submission checklist. Planned values never become measured claims without observation.

## Future files and database changes

`scripts/backup.py`, `restore.py`, `benchmark_reference_demo.py`; `backend/app/modules/foundation/maintenance_service.py`; `backend/tests/integration/test_backup_restore.py`, `test_saved_end_to_end.py`; `docs/evaluation/acceptance-report.md`, `quality-review.md`, `resource-benchmark.md`, `known-limitations.md`; `README.md`, `docs/demo-script.md`, `docs/requirements-changes.md`.

No new business tables. Use foundation maintenance/cleanup state. SQLite holds authoritative vectors; include optional derived index files and model/config manifests in backup set. Full model weights need not be duplicated in every data backup, but restore setup documents their exact required digests and local cache availability.

## Endpoints

No backup/restore HTTP endpoints. Local commands accept an explicitly selected controlled source/target, validate paths and never accept an arbitrary web-supplied filename. API health and maintenance responses expose readiness without filesystem details.

## Implementation steps

1. Complete offline unit/integration tests for arithmetic, missing data, schema validation, uniqueness, retrieval versions, private-address protections, job recovery and revision conflicts. Separate real-model evaluation from the fast test suite.
2. Assemble at least ten curated company evidence records: relevant, irrelevant and incomplete. Label business fit before inspecting scores when possible. Record evidence accuracy and ranking usefulness; disclose score-viewing bias and fixture origin. This is exploratory evaluation, not representative accuracy.
3. Inspect at least six screenshots with human notes. Review at least five generated drafts for grounding/personalization/readability; count unsupported factual claims and require zero in the final approved demo drafts.
4. Run each AT-01–12 and record actual pass/fail, fixture, command, observed result and limitation. Link requirement IDs. Optional extension absence is not core pass evidence. Failed Must requirements need fixes or explicitly accepted scope amendments.
5. Measure CRUD at 100 leads (target <1 second), job initiation (<2 seconds excluding transfer), one warmed analysis (<5 minutes), total system peak memory (<14 GB), combined initial model bytes (<=5 GB) and reference project data (<2 GB). Include OS/Python/package/model IDs, cold/warm distinction, context/image limits, concurrency, sample count and measurement method. Test offline by disabling network with cached fixtures and models already available.
6. Implement consistent backup: enter maintenance to reject new mutations, drain/cancel jobs as operator selected, stop worker writes, use SQLite backup API, copy evidence/knowledge/derived index and manifest, compute hashes, then resume only after success/failure cleanup. Do not hold a write transaction during model generation or copying an entire directory.
7. Restore into a new validated directory first. Check schema support, integrity, foreign keys, relative artifact bounds/hashes and required model identifiers; stop API/worker before replacing active set. Refuse accidental overwrite without an explicit local target/confirmation. Keep old set until restored demo passes.
8. Run restore exercise: lead detail resolves screenshots/thumbnails, retrieval returns the correct document version, draft history and original ICP references survive. Include WAL-safe behavior and pending-cleanup tasks.
9. Document fresh setup, migrations, separate API/worker startup, initial model downloads/licences, cached offline demo, tests, backup/restore, troubleshooting and limitations. Provide Windows PowerShell commands only after dependency/OS/disk checks are complete.
10. Initialize Git early during implementation; make meaningful module commits. Audit tracked files before GitHub publication. Confirm repository visibility before first push as SRS requests. Publish only source/examples/backend/tests/lawful small fixtures/docs; exclude credentials, private leads, runtime DB, models and generated large evidence. No GitHub action is performed by this planning task.
11. Freeze features by end of 20 October; use 21 October for fixes and 22 October for repeatable demo/documentation/backup. Rehearse within the actual instructor demo window when known. Submit on 23 October with honest remaining-feature status.

## Errors and recovery

Backup failure leaves active data intact and a failed snapshot manifest; do not label it usable. Restore missing artifacts/incompatible schema/checksum failure rejects the set before switching active data. Out-of-space failure stops cleanly and preserves old backup/data. Benchmark target miss is documented, followed by reducing context/resolution or smaller-model benchmark; any revised target needs recorded scope discussion rather than false pass.

## Tests and acceptance criteria

AT-12 includes offline fixture flow and actual backup restoration, not merely DB copy. Test restored screenshots/retrieval/history, corrupt/missing file rejection and write suspension. AT-01–11 reports must link to their owning module tests. Fresh documented setup reaches approved draft and explicit manual pipeline update without paid service or internet after initial downloads. All Must requirements pass or have explicitly accepted amendments; stale/missing/partial states remain visible. Source, pins, model licences, measured results, limitations and repeatable demo are reviewable. Optional CNN/ML/n8n status is named independently.
