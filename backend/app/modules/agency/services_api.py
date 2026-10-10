"""Service catalog endpoints; no deletion of historical service records."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.revisions import expected_revision
from app.modules.foundation.database_session import Database
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.agency.service_schema import ServiceCreate, ServiceList, ServicePatch, ServiceResponse
from app.modules.agency import service_catalog_service as service_catalog

router = APIRouter(prefix="/api/v1/services", tags=["Services"], responses={
    404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
    428: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]


@router.post("", response_model=ServiceResponse, status_code=201, summary="Add a service")
def create_service(body: ServiceCreate, response: Response, database: DatabaseDependency):
    with database.transaction(immediate=True) as session:
        result = service_catalog.create_service(session, body)
    response.headers["ETag"] = f'"{result.revision}"'
    response.headers["Location"] = f"/api/v1/services/{result.id}"
    return result


@router.get("", response_model=ServiceList, summary="List services")
def list_services(
    database: DatabaseDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    include_inactive: bool = False,
):
    with database.sessions() as session:
        return service_catalog.get_catalog(
            session, page=page, page_size=page_size, include_inactive=include_inactive
        )


@router.get("/{service_id}", response_model=ServiceResponse, summary="View a service")
def get_service(service_id: UUID, response: Response, database: DatabaseDependency):
    with database.sessions() as session:
        result = ServiceResponse.model_validate(service_catalog.require_service(session, str(service_id)))
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.patch("/{service_id}", response_model=ServiceResponse, summary="Edit or deactivate a service")
def patch_service(service_id: UUID, body: ServicePatch, response: Response, database: DatabaseDependency, revision: RevisionDependency):
    with database.transaction(immediate=True) as session:
        result = service_catalog.edit_service(session, str(service_id), body, revision)
    response.headers["ETag"] = f'"{result.revision}"'
    return result
