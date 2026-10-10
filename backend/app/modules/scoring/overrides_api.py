from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.revisions import expected_revision
from app.modules.foundation.database_session import Database
from app.modules.scoring.score_schema import OverrideCreate, ScoreResponse
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.scoring import overrides_service as overrides

router = APIRouter(prefix='/api/v1/leads', tags=['Reviewer decisions'], responses={code: {'model': ErrorResponse} for code in (404, 409, 422, 428)})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]


@router.post('/{lead_id}/overrides', response_model=ScoreResponse, status_code=201, summary='Record or clear a reasoned reviewer decision')
def create(lead_id: UUID, body: OverrideCreate, database: DatabaseDependency, revision: RevisionDependency):
    with database.transaction(immediate=True) as session: return overrides.create(session, str(lead_id), body, revision)
