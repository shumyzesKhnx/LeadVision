from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_database
from app.core.errors import AppError
from app.db.session import Database
from app.db.repositories import jobs as repository
from app.models.analysis_run import AnalysisRun
from app.schemas.analysis_run import AnalysisRunResponse, AnalysisRunList
from app.schemas.common import ErrorResponse
from app.services import jobs
from app.services.leads import require_lead

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
