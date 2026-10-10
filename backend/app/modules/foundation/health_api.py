"""Readiness is honest: foundation works even when models are unavailable."""

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import func, select, text
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.modules.foundation.clock import utc_now
from app.modules.foundation.errors import AppError
from app.modules.foundation.database_base import SchemaVersion
from app.modules.foundation.database_session import Database
from app.modules.foundation.maintenance_model import WorkerState
from app.modules.foundation.common_schema import DependencyHealth, ErrorResponse, HealthResponse
from app.modules.processing.jobs_service import worker_readiness

router = APIRouter(prefix="/api/v1", tags=["Foundation"])


async def probe_ollama(base_url: str) -> DependencyHealth:
    try:
        async with httpx.AsyncClient(timeout=0.3, trust_env=False, follow_redirects=False) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise ValueError("Unexpected runtime response.")
    except (httpx.HTTPError, ValueError):
        return DependencyHealth(
            status="unavailable", message="Ollama is unavailable. The foundation API still works."
        )
    return DependencyHealth(
        status="available", message="Ollama responds. Configured generation-model readiness is reported separately."
    )


def database_readiness(database: Database) -> tuple[int, bool]:
    with database.sessions() as session:
        session.execute(text("SELECT 1"))
        if session.execute(text("PRAGMA foreign_keys")).scalar_one() != 1:
            raise AppError("DATABASE_UNAVAILABLE", "Database safeguards are not ready.", 503)
        version = session.execute(select(func.max(SchemaVersion.version))).scalar_one()
        worker = session.get(WorkerState, 1)
        if version is None or worker is None:
            raise AppError("DATABASE_UNAVAILABLE", "Database initialization is incomplete.", 503)
        return version, worker.maintenance_requested


@router.get("/health", response_model=HealthResponse, responses={503: {"model": ErrorResponse}})
async def health(request: Request) -> HealthResponse:
    version, maintenance = await run_in_threadpool(database_readiness, request.app.state.database)
    runtime = await probe_ollama(request.app.state.settings.ollama_base_url)
    def check_worker():
        with request.app.state.database.sessions() as session:
            return worker_readiness(session, request.app.state.settings)
    worker = await run_in_threadpool(check_worker)
    def check_model():
        from app.modules.nlp.business_analysis_model import RuntimeModel
        with request.app.state.database.sessions() as session:
            model = session.get(RuntimeModel, 1)
            if model and model.status == 'available':
                return DependencyHealth(status='available', message=f'Worker detected {model.name}; model digest is pinned per new job.')
            return DependencyHealth(status='unavailable', message='The worker has not detected the configured generation model.')
    generation = await run_in_threadpool(check_model)
    def check_embedding():
        from app.modules.semantics.embedding_model import EmbeddingRuntime
        with request.app.state.database.sessions() as session:
            model = session.get(EmbeddingRuntime, 1)
            available = model is not None and model.status == 'available'
            return DependencyHealth(status='available' if available else 'unavailable',
                message='Local CPU embedding model verified.' if available else 'Local embedding model is not ready; run scripts/setup_embeddings.py.')
    embedding = await run_in_threadpool(check_embedding)
    return HealthResponse(
        status="maintenance" if maintenance else "ok",
        version=__version__,
        schema_version=version,
        checked_at=utc_now(),
        maintenance=maintenance,
        database=DependencyHealth(status="ready", message="SQLite is available with foreign keys enabled."),
        worker=worker,
        ollama=runtime,
        generation_model=generation,
        embedding_model=embedding,
    )
