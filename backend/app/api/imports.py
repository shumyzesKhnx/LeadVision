from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, UploadFile, Response
from starlette.concurrency import run_in_threadpool
from app.api.dependencies import get_database
from app.core.errors import AppError
from app.db.session import Database
from app.schemas.common import ErrorResponse
from app.schemas.imports import ImportReport
from app.services.csv_import import HEADERS, MAX_CSV_BYTES, import_csv

router = APIRouter(prefix='/api/v1', tags=['CSV imports'], responses={code: {'model': ErrorResponse} for code in (404, 409, 413, 415, 422, 503)})
DatabaseDependency = Annotated[Database, Depends(get_database)]


@router.get('/imports/template', summary='Download the company CSV template')
def template():
    return Response(','.join(HEADERS) + '\r\n', media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="leadvision-companies.csv"'})


@router.post('/campaigns/{campaign_id}/imports', response_model=ImportReport, summary='Import up to 100 companies from CSV')
async def upload(campaign_id: UUID, database: DatabaseDependency, file: Annotated[UploadFile, File(description='UTF-8 .csv, at most 5 MB and 100 data rows.')]):
    try:
        if not file.filename or not file.filename.lower().endswith('.csv') or file.content_type not in {
            'text/csv', 'application/csv', 'application/vnd.ms-excel', 'text/plain', 'application/octet-stream'
        }:
            raise AppError('CSV_MEDIA_TYPE', 'Choose a CSV file saved as UTF-8.', 415)
        chunks = bytearray()
        while chunk := await file.read(64 * 1024):
            chunks.extend(chunk)
            if len(chunks) > MAX_CSV_BYTES:
                raise AppError('CSV_TOO_LARGE', 'CSV files must be at most 5 MB.', 413)
        return await run_in_threadpool(import_csv, database, str(campaign_id), bytes(chunks))
    finally:
        await file.close()
