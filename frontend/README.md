# Frontend

The local interface is built with plain HTML, CSS and JavaScript. It uses a
dark bottle green background and olive accents. No npm setup or separate
frontend server is needed. FastAPI serves it at **http://127.0.0.1:8000/**.

- `index.html`: shared navigation and page shell.
- `app.js`: navigation and connecting feature screens.
- `modules/<feature>/index.js`: each feature's screens, forms or result cards.
- `shared/api.js`: requests, revision headers and safe text escaping.
- `shared/context.js` and `shared/data.js`: workspace state and record loading.
- `shared/ui.js`: reusable controls, dialogs and formatting.
- `shared/styles/app.css`: bottle green/olive theme and mobile layout.

See [the module folder guide](../docs/project-structure.md) for every folder.

Use `scripts/start.ps1` for the server and `scripts/worker.ps1` in a second
terminal for research. All frontend assets are local. Website collection
needs internet; saved evidence can be used offline with installed models.
Swagger remains at `/docs`.

See [the demonstration guide](../docs/frontend-demo.md) for a short walkthrough.
