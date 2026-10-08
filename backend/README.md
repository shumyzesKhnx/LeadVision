# Backend

`app/` contains Python API code; `tests/` contains its automated tests.
`requirements.in` and `requirements.lock.txt` define the backend dependencies.
Optional local settings belong in `backend/.env`, based on `.env.example` here.
Runtime data stays in the project-level `data/` folder, regardless of your terminal directory.

From this folder, using the existing project virtual environment:

```powershell
..\.venv\Scripts\python.exe -m app
```

Run the tests:

```powershell
..\.venv\Scripts\python.exe -m pytest
```

See the [project README](../README.md) for the full setup and folder layout.

For processing jobs, keep a second terminal running the separate worker:

```powershell
..\.venv\Scripts\python.exe -m app.worker.main
```

Only one worker can run per data directory. See the [phase 6 walkthrough](../docs/phase-06-jobs-and-workflow.md) for jobs, [phase 7](../docs/phase-07-saved-evidence.md) for saved uploads, and [phase 8](../docs/phase-08-nlp.md) for local NLP. Live fetching, CV, semantics and scoring arrive in later milestones.

For processing jobs, keep a second terminal running the separate worker:

```powershell
..\.venv\Scripts\python.exe -m app.worker.main
```

Only one worker can run per data directory. See the [phase 6 walkthrough](../docs/phase-06-jobs-and-workflow.md) for job submission, polling and retry. Website and AI processing handlers are implemented in later phases.
