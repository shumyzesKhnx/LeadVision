from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.database_session import Database
from app.modules.foundation.revisions import expected_revision
from app.modules.processing.jobs_service import idempotency_key
from app.modules.processing.jobs_service import job_response
from app.modules.processing.job_model import Job
from app.modules.leads.leads_service import require_lead
from app.modules.outreach.outreach_schema import OutreachCreate, OutreachReceipt, DraftText, DraftReview
from app.modules.outreach import outreach_service as service, outreach_repository as repository, draft_review

router = APIRouter(prefix='/api/v1', tags=['Outreach drafts'])
DatabaseDependency = Annotated[Database, Depends(get_database)]


@router.post('/leads/{lead_id}/outreach-jobs', response_model=OutreachReceipt, status_code=202)
def create_draft(lead_id: UUID, body: OutreachCreate, request: Request, database: DatabaseDependency,
                 key: Annotated[str, Depends(idempotency_key)]):
    with database.transaction(immediate=True) as session:
        return service.submit(session, request.app.state.settings, str(lead_id), body, key)


@router.get('/leads/{lead_id}/drafts')
def list_drafts(lead_id: UUID, database: DatabaseDependency):
    with database.sessions() as session:
        lead = require_lead(session, str(lead_id))
        return {'items': [service.response(session, row) for row in repository.list_for_lead(session, lead.id)]}


@router.get('/leads/{lead_id}/outreach-status')
def outreach_status(lead_id: UUID, database: DatabaseDependency):
    with database.sessions() as session:
        lead = require_lead(session, str(lead_id))
        job = session.scalar(select(Job).where(Job.lead_id == lead.id, Job.kind == 'outreach')
                             .order_by(Job.queued_at.desc(), Job.id.desc()).limit(1))
        return {'job': job_response(session, job) if job else None}


@router.get('/drafts/{draft_id}')
def get_draft(draft_id: UUID, response: Response, database: DatabaseDependency):
    with database.sessions() as session:
        row = service.require_draft(session, draft_id)
        response.headers['ETag'] = f'"{row.revision}"'
        return service.response(session, row)


@router.post('/drafts/{draft_id}/revisions', status_code=201)
def edit_draft(draft_id: UUID, body: DraftText, database: DatabaseDependency, revision: Annotated[int, Depends(expected_revision)]):
    with database.transaction(immediate=True) as session:
        return draft_review.edit(session, service.require_draft(session, draft_id), body, revision)


@router.post('/drafts/{draft_id}/review', status_code=201)
def review_draft(draft_id: UUID, body: DraftReview, database: DatabaseDependency, revision: Annotated[int, Depends(expected_revision)]):
    with database.transaction(immediate=True) as session:
        return draft_review.review(session, service.require_draft(session, draft_id), body, revision)


@router.get('/drafts/{draft_id}/approved-text')
def copy_text(draft_id: UUID, database: DatabaseDependency):
    with database.sessions() as session:
        return draft_review.approved_text(session, service.require_draft(session, draft_id))
