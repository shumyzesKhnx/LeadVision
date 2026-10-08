"""Create the API; initialize durable resources only during startup."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app import __version__
from app.api.health import router as health_router
from app.api.agency import router as agency_router
from app.api.services import router as services_router
from app.api.icps import router as icps_router
from app.api.campaigns import router as campaigns_router
from app.api.leads import router as leads_router
from app.api.imports import router as imports_router
from app.api.jobs import router as jobs_router
from app.api.runs import router as runs_router
from app.api.evidence import router as evidence_router
from app.api.artifacts import router as artifacts_router
from app.core.upload_limits import ImportUploadLimit
from app.core.config import Settings
from app.core.errors import install_error_handlers
from app.core.request_guards import RequestGuards
from app.core.storage import ArtifactStorage, reject_links
from app.db.migration_runner import migrate
from app.db.session import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        storage = ArtifactStorage(settings.data_dir)
        reject_links(settings.database_path)
        database = Database(settings)
        application.state.storage = storage
        application.state.database = database
        try:
            version = migrate(database.engine, require_initialized=settings.database_must_exist)
            logging.getLogger("leadvision").info("Database ready; schema version %s.", version)
            yield
        finally:
            database.close()

    application = FastAPI(
        title="Lead Vision",
        description="Local lead qualification backend: agency, services, customer profiles, campaigns, leads and processing jobs.",
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = settings
    install_error_handlers(application)
    application.add_middleware(ImportUploadLimit)
    application.add_middleware(RequestGuards, settings=settings)
    application.include_router(health_router)
    application.include_router(agency_router)
    application.include_router(services_router)
    application.include_router(icps_router)
    application.include_router(campaigns_router)
    application.include_router(leads_router)
    application.include_router(imports_router)
    application.include_router(jobs_router)
    application.include_router(runs_router)
    application.include_router(evidence_router)
    application.include_router(artifacts_router)

    @application.get("/", include_in_schema=False)
    async def home():
        return RedirectResponse("/docs")

    return application


app = create_app()
