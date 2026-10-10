from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select, func
from starlette.concurrency import run_in_threadpool
from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.errors import AppError
from app.modules.foundation.revisions import expected_revision
from app.modules.foundation.database_session import Database
from app.modules.evidence.evidence_model import Evidence
from app.modules.foundation.common_schema import ErrorResponse
from app.modules.evidence.evidence_schema import SavedEvidenceMetadata, SavedEvidenceReceipt, EvidenceList, EvidenceReview, EvidenceResponse
from app.modules.evidence import evidence_service as evidence
from app.modules.processing.jobs_service import run_response
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.evidence.image_validation_service import MAX_IMAGE_BYTES
from app.modules.evidence.text_extraction_service import MAX_TEXT_BYTES

router = APIRouter(prefix='/api/v1', tags=['Saved evidence'], responses={code: {'model': ErrorResponse} for code in (404, 409, 413, 415, 422, 428, 503)})
DatabaseDependency = Annotated[Database, Depends(get_database)]
RevisionDependency = Annotated[int, Depends(expected_revision)]


async def read_upload(file, limit, code):
    if file is None:
        return None
    result = bytearray()
    while chunk := await file.read(65536):
        result.extend(chunk)
        if len(result) > limit:
            raise AppError(code, 'The uploaded file exceeds its size limit.', 413)
    return bytes(result)


@router.post('/leads/{lead_id}/saved-evidence', response_model=SavedEvidenceReceipt, status_code=201,
             summary='Upload saved website text and/or screenshot')
async def upload(lead_id: UUID, request: Request, database: DatabaseDependency,
    text_file: Annotated[UploadFile | None, File(description='Readable UTF-8 .txt, at most 1 MB.')] = None,
    image_file: Annotated[UploadFile | None, File(description='Static PNG/JPEG, at most 10 MB and 20 million pixels.')] = None,
    source_mode: Annotated[Literal['uploaded', 'cached'], Form()] = 'uploaded',
    original_url: Annotated[str | None, Form(max_length=2048)] = None,
    collected_at: Annotated[datetime | None, Form(description='Optional original collection time with timezone; leave blank if unknown.')] = None,
    title: Annotated[str | None, Form(max_length=200)] = None):
    try:
        if text_file and (not text_file.filename or not text_file.filename.lower().endswith('.txt')):
            raise AppError('TEXT_MEDIA_TYPE', 'Choose a readable UTF-8 .txt file.', 415)
        # Actual image signature and decoder format determine validity, not filename or MIME.
        try:
            metadata = SavedEvidenceMetadata(source_mode=source_mode, original_url=original_url, collected_at=collected_at, title=title)
        except ValidationError as error:
            raise RequestValidationError([{**item, 'loc': ('body', *item['loc'])} for item in error.errors()]) from None
        text = await read_upload(text_file, MAX_TEXT_BYTES, 'TEXT_TOO_LARGE')
        image = await read_upload(image_file, MAX_IMAGE_BYTES, 'IMAGE_TOO_LARGE')
        return await run_in_threadpool(evidence.create_upload, database, request.app.state.storage,
                                      request.app.state.settings, str(lead_id), metadata, text, image)
    finally:
        for file in (text_file, image_file):
            if file:
                await file.close()


@router.get('/runs/{run_id}/evidence', response_model=EvidenceList, summary='View the evidence saved by this attempt')
def list_evidence(run_id: UUID, database: DatabaseDependency, page: Annotated[int, Query(ge=1)] = 1,
                  page_size: Annotated[int, Query(ge=1, le=100)] = 25):
    with database.sessions() as session:
        run = session.get(AnalysisRun, str(run_id))
        if run is None:
            raise AppError('RUN_NOT_FOUND', 'Analysis run not found.', 404)
        run_response(session, run)  # Also checks workspace ownership.
        total = session.scalar(select(func.count()).select_from(Evidence).where(Evidence.run_id == run.id))
        items = list(session.scalars(select(Evidence).where(Evidence.run_id == run.id).order_by(Evidence.kind, Evidence.id)
                                    .offset((page - 1) * page_size).limit(page_size)))
        return EvidenceList(items=[evidence.evidence_response(item) for item in items], total=total, page=page, page_size=page_size)


@router.patch('/evidence/{evidence_id}/review', response_model=EvidenceResponse, summary='Mark evidence usable or unusable')
def review(evidence_id: UUID, body: EvidenceReview, response: Response, database: DatabaseDependency, revision: RevisionDependency):
    with database.transaction(immediate=True) as session:
        result = evidence.review(session, evidence.require_evidence(session, str(evidence_id)), body, revision)
    response.headers['ETag'] = f'"{result.revision}"'
    return result
