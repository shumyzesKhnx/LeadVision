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
