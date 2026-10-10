"""Create the API; initialize durable resources only during startup."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.modules.foundation.health_api import router as health_router
from app.modules.agency.agency_api import router as agency_router
from app.modules.agency.services_api import router as services_router
from app.modules.icp.icps_api import router as icps_router
from app.modules.campaigns.campaigns_api import router as campaigns_router
from app.modules.leads.leads_api import router as leads_router
from app.modules.leads.imports_api import router as imports_router
from app.modules.processing.jobs_api import router as jobs_router
from app.modules.processing.runs_api import router as runs_router
from app.modules.evidence.evidence_api import router as evidence_router
from app.modules.evidence.artifacts_api import router as artifacts_router
from app.modules.scoring.scores_api import router as scores_router
from app.modules.scoring.overrides_api import router as overrides_router
from app.modules.knowledge.knowledge_api import router as knowledge_router
from app.modules.outreach.outreach_api import router as outreach_router
from app.modules.foundation.upload_limits import ImportUploadLimit
from app.modules.foundation.config import Settings, PROJECT_ROOT
from app.modules.foundation.errors import install_error_handlers
from app.modules.foundation.request_guards import RequestGuards
from app.modules.foundation.storage import ArtifactStorage, reject_links
from app.modules.foundation.migration_runner import migrate
from app.modules.foundation.database_session import Database


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
    application.include_router(scores_router)
    application.include_router(overrides_router)
    application.include_router(knowledge_router)
    application.include_router(outreach_router)
    frontend = PROJECT_ROOT / 'frontend'
    application.mount('/assets', StaticFiles(directory=frontend), name='frontend')

    @application.get("/", include_in_schema=False)
    async def home():
        return FileResponse(frontend / 'index.html', headers={'Cache-Control': 'no-cache'})

    return application


app = create_app()
