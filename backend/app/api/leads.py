from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, Request
from fastapi.responses import JSONResponse
from app.api.dependencies import get_database
from app.core.revisions import expected_revision
from app.db.repositories import leads as repository
from app.db.session import Database
from app.schemas.common import ErrorResponse
from app.schemas.lead import LeadCreate, LeadPatch, LeadDetail, LeadList, LeadFactList, LeadFactResponse, PipelineState, Priority
from app.services import leads
from app.services.agency import require_workspace
from app.services.campaign import require_campaign

router = APIRouter(prefix='/api/v1/leads', tags=['Leads'], responses={code: {'model': ErrorResponse} for code in (404, 409, 422, 428, 503)})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post('', response_model=LeadDetail, status_code=201, summary='Add a company to a campaign')
def create(body: LeadCreate, response: Response, database: DatabaseDependency):
    with database.transaction(immediate=True) as session:
        result = leads.create_lead(session, body)
    response.headers['ETag'] = f'"{result.revision}"'
    response.headers['Location'] = f'/api/v1/leads/{result.id}'
    return result


@router.get('', response_model=LeadList, summary='List and search companies')
def list_leads(database: DatabaseDependency, campaign_id: UUID | None = None, pipeline_state: PipelineState | None = None,
               priority: Priority | None = None, q: Annotated[str | None, Query(max_length=200)] = None,
               sort: Literal['created_at', 'score'] = 'created_at', direction: Literal['asc', 'desc'] = 'desc',
               page: Page = 1, page_size: PageSize = 25):
    with database.sessions() as session:
        agency = require_workspace(session)
        if campaign_id is not None:
            require_campaign(session, str(campaign_id))
        # No scores exist before module 11: all scores are null, all priorities Needs review.
        if priority is not None and priority != 'Needs review':
            return LeadList(items=[], page=page, page_size=page_size, total=0)
        items, total = repository.list_leads(session, agency.id, campaign_id=str(campaign_id) if campaign_id else None,
                                            pipeline_state=pipeline_state, q=q, direction=direction, page=page, page_size=page_size)
        return LeadList(items=[leads.lead_response(session, item) for item in items], page=page, page_size=page_size, total=total)


@router.get('/{lead_id}', response_model=LeadDetail, summary='View a company and its entered facts')
def get_lead(lead_id: UUID, response: Response, database: DatabaseDependency):
    with database.sessions() as session:
        result = leads.lead_response(session, leads.require_lead(session, str(lead_id)), detail=True)
    response.headers['ETag'] = f'"{result.revision}"'
    return result


@router.patch('/{lead_id}', response_model=LeadDetail, summary='Correct company details or notes')
def edit(lead_id: UUID, body: LeadPatch, response: Response, database: DatabaseDependency, revision: RevisionDependency):
    with database.transaction(immediate=True) as session:
        result = leads.edit_lead(session, str(lead_id), body, revision)
    response.headers['ETag'] = f'"{result.revision}"'
    return result


@router.get('/{lead_id}/facts', response_model=LeadFactList, summary='View the history of entered company facts')
def history(lead_id: UUID, database: DatabaseDependency, page: Page = 1, page_size: PageSize = 25):
    with database.sessions() as session:
        lead = leads.require_lead(session, str(lead_id))
        items, total = repository.fact_history(session, lead.id, page, page_size)
        return LeadFactList(items=[LeadFactResponse.model_validate(item) for item in items], page=page, page_size=page_size, total=total)


@router.delete('/{lead_id}', status_code=204, summary='Delete a company from this campaign')
def remove(lead_id: UUID, request: Request, database: DatabaseDependency, revision: RevisionDependency, confirm: bool = False):
    with database.transaction(immediate=True) as session:
        cleanup_count = leads.delete_lead(session, str(lead_id), revision, confirm, request.app.state.storage)
    if cleanup_count:
        return JSONResponse(status_code=202, content={'deleted': True, 'cleanup': {'state': 'pending', 'tasks': cleanup_count}})
    return Response(status_code=204)
