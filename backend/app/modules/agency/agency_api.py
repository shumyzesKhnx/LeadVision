"""Agency routes validate HTTP and delegate workspace behavior to services."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.revisions import expected_revision
from app.modules.foundation.database_session import Database
from app.modules.agency.agency_schema import AgencyCreate, AgencyPatch, AgencyResponse
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.agency import agency_service as service

router = APIRouter(prefix="/api/v1/agency", tags=["Agency"], responses={
    404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
    428: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]


@router.post("", response_model=AgencyResponse, status_code=201, summary="Create your agency")
def create_agency(body: AgencyCreate, response: Response, database: DatabaseDependency):
    with database.transaction(immediate=True) as session:
        result = service.create_workspace(session, body)
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.get("", response_model=AgencyResponse, summary="View your agency")
def get_agency(response: Response, database: DatabaseDependency):
    with database.sessions() as session:
        result = service.workspace_response(session, service.require_workspace(session))
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.patch("", response_model=AgencyResponse, summary="Edit your agency")
def patch_agency(body: AgencyPatch, response: Response, database: DatabaseDependency, revision: RevisionDependency):
    with database.transaction(immediate=True) as session:
        result = service.edit_workspace(session, body, revision)
    response.headers["ETag"] = f'"{result.revision}"'
    return result
