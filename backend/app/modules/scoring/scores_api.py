from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.database_session import Database
from app.modules.scoring import scores_repository as repository
from app.modules.scoring.score_schema import ScoreResponse, ScoreList
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.scoring import scoring_service as scoring
from app.modules.leads.leads_service import require_lead

router = APIRouter(prefix='/api/v1', tags=['Scores'], responses={404: {'model': ErrorResponse}})
DatabaseDependency = Annotated[Database, Depends(get_database)]


@router.get('/leads/{lead_id}/scores', response_model=ScoreList, summary='View explained score history')
def history(lead_id: UUID, database: DatabaseDependency, page: Annotated[int, Query(ge=1)] = 1,
            page_size: Annotated[int, Query(ge=1, le=100)] = 25):
    with database.sessions() as session:
        lead = require_lead(session, str(lead_id)); rows, total = repository.history(session, lead.id, page, page_size)
        return ScoreList(items=[scoring.response(session, row) for row in rows], total=total, page=page, page_size=page_size)


@router.get('/scores/{score_id}', response_model=ScoreResponse, summary='View score components and qualification recommendation')
def get_score(score_id: UUID, database: DatabaseDependency):
    with database.sessions() as session: return scoring.response(session, scoring.require_score(session, str(score_id)))
