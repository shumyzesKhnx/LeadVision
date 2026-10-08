"""Campaign creation, targeting, archive and read endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.api.dependencies import get_database
from app.core.revisions import expected_revision
from app.db.repositories import campaign as repository
from app.db.session import Database
from app.schemas.campaign import CampaignCreate, CampaignPatch, CampaignResponse, CampaignList
from app.schemas.common import ErrorResponse
from app.services import campaign
from app.services.agency import require_workspace

router = APIRouter(prefix='/api/v1/campaigns', tags=['Campaigns'], responses={
    code: {'model': ErrorResponse} for code in (404, 409, 422, 428, 503)
})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]


@router.post('', response_model=CampaignResponse, status_code=201, summary='Create a campaign')
def create(body: CampaignCreate, response: Response, database: DatabaseDependency):
    with database.transaction(immediate=True) as session:
        result = campaign.create_campaign(session, body)
    response.headers['ETag'] = f'"{result.revision}"'
    response.headers['Location'] = f'/api/v1/campaigns/{result.id}'
    return result


@router.get('', response_model=CampaignList, summary='List campaigns')
def list_campaigns(database: DatabaseDependency, page: Annotated[int, Query(ge=1)] = 1,
                   page_size: Annotated[int, Query(ge=1, le=100)] = 25, include_archived: bool = False):
    with database.sessions() as session:
        agency = require_workspace(session)
        items, total = repository.list_campaigns(session, agency.id, page, page_size, include_archived)
        return CampaignList(items=[campaign.campaign_response(session, item) for item in items],
                            page=page, page_size=page_size, total=total)


@router.get('/{campaign_id}', response_model=CampaignResponse, summary='View a campaign')
def get_campaign(campaign_id: UUID, response: Response, database: DatabaseDependency):
    with database.sessions() as session:
        result = campaign.campaign_response(session, campaign.require_campaign(session, str(campaign_id)))
    response.headers['ETag'] = f'"{result.revision}"'
    return result


@router.patch('/{campaign_id}', response_model=CampaignResponse, summary='Edit, archive or reactivate a campaign')
def edit(campaign_id: UUID, body: CampaignPatch, response: Response, database: DatabaseDependency,
         revision: RevisionDependency):
    with database.transaction(immediate=True) as session:
        result = campaign.edit_campaign(session, str(campaign_id), body, revision)
    response.headers['ETag'] = f'"{result.revision}"'
    return result
