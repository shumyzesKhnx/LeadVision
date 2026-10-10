# Project folders, explained simply

Each implemented feature now has its own folder. The backend and frontend
use the same feature names wherever they share a responsibility.

```text
LeadVision/
  backend/
    app/
      main.py                    # Connects routers and serves the frontend
      __main__.py                # Starts the API
      modules/
        foundation/              # Configuration, database, safety and health
        agency/                  # Agency profile and offered services
        icp/                     # Ideal customer profiles and targeting rules
        campaigns/               # Groups of companies using an ICP
        leads/                   # Companies, corrections and CSV imports
        processing/              # Jobs, research history and the worker
        evidence/                # Website text, screenshots and evidence review
        nlp/                     # Qwen business analysis and versioned prompts
        computer_vision/         # Screenshot pixel measurements
        semantics/               # MiniLM embeddings and text similarity
        scoring/                 # Explained scores and reviewer overrides
        knowledge/               # Approved agency facts and source retrieval
    tests/
      unit/                      # Small rule checks for these modules
      integration/               # Modules working together and browser checks
    .env.example
    requirements.in
    requirements.lock.txt
  frontend/
    index.html                   # Common page shell
    app.js                       # Navigation and connecting screens
    modules/
      overview/                  # Overview and system readiness
      agency/                    # Agency and service screens/forms
      icp/                       # Target profile screens/forms
      campaigns/                 # Campaign screens/forms
      leads/                     # Company list, forms, CSV and corrections
      processing/                # Research controls, progress and history
      evidence/                  # Evidence cards and usability review
      nlp/                       # Business summary and quoted sources
      computer_vision/           # Screenshot measurement presentation
      semantics/                 # Target similarity presentation
      scoring/                   # Score breakdown presentation
      knowledge/                 # Documents, approval, indexing and retrieval
      flow/                      # How the system works
    shared/
      api.js                     # HTTP requests and safe text escaping
      context.js                 # Shared state and notifications
      data.js                    # Loads workspace records
      ui.js                      # Reusable forms, cards and formatting
      styles/app.css             # Shared bottle green/olive theme
  scripts/                       # Start, worker, setup and test commands
  docs/                          # Plans, guides and verification
  data/                          # Local database and evidence; ignored by Git
  models/                        # Downloaded local models; ignored by Git
  .venv/                         # Python environment; ignored by Git
  .cache/                        # Temporary tooling and checks; ignored by Git
```

## Inside a backend module

All files sit directly in the module folder. Filename endings explain their job:

- `_api.py`: endpoints that receive browser requests.
- `_schema.py`: allowed input/output fields and validation.
- `_service.py`: the module's business rules.
- `_model.py`: its database record definitions.
- `_repository.py`: its database queries.
- `_client.py`: external model, browser or website clients.

For example, `agency/` contains `agency_api.py`, `agency_schema.py`,
`agency_service.py`, `agency_model.py` and `agency_repository.py` together.
The offered-service files are also directly in `agency/`.
Python creates `__pycache__` automatically; VS Code hides these generated folders.

For example, the agency module contains agency and service endpoints, forms,
database definitions, queries and business rules together. Screenshot capture
belongs to evidence; screenshot measurement belongs to computer vision.

Shared configuration, storage safeguards and database infrastructure belong to
**foundation**. All numbered database migrations remain together in
`backend/app/modules/foundation/`, because the database has one
ordered migration history. Their content and checksums were preserved.
Worker files sit directly in `processing/`, named `worker_main.py`,
`worker_queue.py`, `worker_handlers.py`, `worker_lock.py` and `worker_recovery.py`.
Versioned prompt files sit directly in `nlp/`.

Modules can import one another explicitly. A folder boundary helps organization;
it does not turn each feature into a separate server or database.

## Inside a frontend module

Each `modules/<feature>/index.js` owns that feature's screens or result cards.
`frontend/app.js` handles navigation and connects them. `index.html` remains
the single shared HTML shell; each module does not need a duplicate HTML page.
Reusable controls and the shared theme stay in `shared/`.

## Running the project

Your normal commands are still:

```powershell
.\scripts\start.ps1
.\scripts\worker.ps1
.\scripts\test.ps1
```

Run the server and worker in separate terminals. The scripts now use the new
module paths. The frontend remains at **http://127.0.0.1:8000/**.

Direct worker command from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m app.modules.processing.worker_main
```

Future outreach and pipeline modules will use their own folders
when implemented. No empty folders are presented as completed features.
