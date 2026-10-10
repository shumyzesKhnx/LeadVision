"""Customer profile setup and read-only version history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.revisions import expected_revision
from app.modules.icp import icp_repository as repository
from app.modules.foundation.database_session import Database
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.icp.icp_schema import ICPCreate, ICPList, ICPPatch, ICPResponse, ICPVersionList, ICPVersionResponse
from app.modules.icp import icp_service as icp
from app.modules.agency.agency_service import require_workspace
from app.modules.icp.criteria_service import COUNTRY_CODES, INDUSTRY_SYNONYMS, REGIONS

router = APIRouter(prefix='/api/v1/icps', tags=['Customer profiles (ICP)'], responses={
    code: {'model': ErrorResponse} for code in (404, 409, 422, 428, 503)
})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get('/options', summary='View supported countries, regions and industry synonyms')
def options():
    return {'country_codes': sorted(COUNTRY_CODES), 'regions': REGIONS,
            'industry_synonyms': INDUSTRY_SYNONYMS,
            'guidance': 'Industry labels use exact normalized matching. Free-text preferences do not enforce exclusions.'}


@router.post('', response_model=ICPResponse, status_code=201, summary='Create an ideal customer profile')
def create_profile(body: ICPCreate, response: Response, database: DatabaseDependency):
    with database.transaction(immediate=True) as session:
        result = icp.create_icp(session, body)
    response.headers['ETag'] = f'"{result.revision}"'
    response.headers['Location'] = f'/api/v1/icps/{result.id}'
    return result


@router.get('', response_model=ICPList, summary='List customer profiles')
def list_profiles(database: DatabaseDependency, page: Page = 1, page_size: PageSize = 25,
                  include_archived: bool = False):
    with database.sessions() as session:
        agency = require_workspace(session)
        items, total = repository.list_icps(session, agency.id, page, page_size, include_archived)
        return ICPList(items=[icp.profile_response(session, item) for item in items],
                       page=page, page_size=page_size, total=total)


@router.get('/{icp_id}', response_model=ICPResponse, summary='View a customer profile')
def get_profile(icp_id: UUID, response: Response, database: DatabaseDependency):
    with database.sessions() as session:
        result = icp.profile_response(session, icp.require_icp(session, str(icp_id)))
    response.headers['ETag'] = f'"{result.revision}"'
    return result


@router.patch('/{icp_id}', response_model=ICPResponse, summary='Edit or archive a customer profile')
def patch_profile(icp_id: UUID, body: ICPPatch, response: Response, database: DatabaseDependency,
                  revision: RevisionDependency):
    with database.transaction(immediate=True) as session:
        result = icp.edit_icp(session, str(icp_id), body, revision)
    response.headers['ETag'] = f'"{result.revision}"'
    return result


@router.get('/{icp_id}/versions', response_model=ICPVersionList, summary='View previous scoring configurations')
def version_history(icp_id: UUID, database: DatabaseDependency, page: Page = 1, page_size: PageSize = 25):
    with database.sessions() as session:
        profile = icp.require_icp(session, str(icp_id))
        items, total = repository.list_versions(session, profile.id, page, page_size)
        return ICPVersionList(items=[ICPVersionResponse.model_validate(item) for item in items],
                              page=page, page_size=page_size, total=total)
