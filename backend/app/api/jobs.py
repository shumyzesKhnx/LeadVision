from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from app.api.dependencies import get_database
from app.db.session import Database
from app.schemas.common import ErrorResponse
from app.schemas.job import AnalysisJobCreate, JobRetry, JobReceipt, JobResponse
from app.services import jobs

router = APIRouter(prefix='/api/v1', tags=['Jobs'], responses={code: {'model': ErrorResponse} for code in (404, 409, 422, 428, 503)})
DatabaseDependency = Annotated[Database, Depends(get_database)]
KeyDependency = Annotated[str, Depends(jobs.idempotency_key)]


@router.post('/leads/{lead_id}/analysis-jobs', response_model=JobReceipt, status_code=202, summary='Queue analysis of a company')
def submit(lead_id: UUID, body: AnalysisJobCreate, request: Request, response: Response, database: DatabaseDependency, key: KeyDependency):
    with database.transaction(immediate=True) as session:
        result = jobs.submit(session, request.app.state.settings, str(lead_id), body, key)
    response.headers['Location'] = result.poll_url
    return result


@router.get('/jobs/{job_id}', response_model=JobResponse, summary='Check job status and saved stages')
def get_job(job_id: UUID, database: DatabaseDependency):
    with database.sessions() as session:
        return jobs.job_response(session, jobs.require_job(session, str(job_id)))


@router.post('/jobs/{job_id}/cancel', response_model=JobResponse, summary='Request cancellation')
def cancel(job_id: UUID, database: DatabaseDependency):
    with database.transaction(immediate=True) as session:
        return jobs.cancel(session, jobs.require_job(session, str(job_id)))


@router.post('/jobs/{job_id}/retry', response_model=JobReceipt, status_code=202, summary='Retry with current inputs and a new request key')
def retry(job_id: UUID, request: Request, response: Response, database: DatabaseDependency, key: KeyDependency,
          body: JobRetry = JobRetry()):
    with database.transaction(immediate=True) as session:
        result = jobs.retry(session, request.app.state.settings, jobs.require_job(session, str(job_id)), body, key)
    response.headers['Location'] = result.poll_url
    return result
