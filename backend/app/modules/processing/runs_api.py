from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.errors import AppError
from app.modules.foundation.database_session import Database
from app.modules.processing import jobs_repository as repository
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.processing.analysis_run_schema import AnalysisRunResponse, AnalysisRunList
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.processing import jobs_service as jobs
from app.modules.leads.leads_service import require_lead

router = APIRouter(prefix='/api/v1', tags=['Analysis history'], responses={404: {'model': ErrorResponse}})
DatabaseDependency = Annotated[Database, Depends(get_database)]


@router.get('/leads/{lead_id}/runs', response_model=AnalysisRunList, summary='List prior analysis runs')
def history(lead_id: UUID, database: DatabaseDependency, page: Annotated[int, Query(ge=1)] = 1,
            page_size: Annotated[int, Query(ge=1, le=100)] = 25):
    with database.sessions() as session:
        lead = require_lead(session, str(lead_id))
        items, total = repository.run_history(session, lead.id, page, page_size)
        return AnalysisRunList(items=[jobs.run_response(session, item) for item in items], page=page, page_size=page_size, total=total)


@router.get('/runs/{run_id}', response_model=AnalysisRunResponse, summary='View saved inputs and processing outcomes')
def get_run(run_id: UUID, database: DatabaseDependency):
    with database.sessions() as session:
        run = session.get(AnalysisRun, str(run_id))
        if run is None:
            raise AppError('RUN_NOT_FOUND', 'Analysis run not found.', 404)
        require_lead(session, run.lead_id)
        return jobs.run_response(session, run)
