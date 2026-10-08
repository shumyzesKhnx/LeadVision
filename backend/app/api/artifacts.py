from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from app.api.dependencies import get_database
from app.db.session import Database
from app.core.errors import AppError
from app.services.evidence import require_evidence, read_verified

router = APIRouter(prefix='/api/v1/artifacts', tags=['Artifacts'])
DatabaseDependency = Annotated[Database, Depends(get_database)]


def image_response(evidence_id, request, database, thumbnail=False):
    with database.sessions() as session:
        evidence = require_evidence(session, str(evidence_id))
        if evidence.kind != 'image':
            raise AppError('IMAGE_NOT_FOUND', 'This evidence has no image.', 404)
        metadata = evidence.metadata_json
        content = read_verified(request.app.state.storage, metadata, thumbnail=thumbnail)
    media = 'image/jpeg' if thumbnail or metadata['format'] == 'JPEG' else 'image/png'
    digest = metadata['thumbnail_sha256' if thumbnail else 'sha256']
    return Response(content, media_type=media, headers={'ETag': f'"{digest}"', 'Cache-Control': 'private, no-store',
                    'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline'})


@router.get('/{evidence_id}/image', summary='View the unchanged original screenshot')
def image(evidence_id: UUID, request: Request, database: DatabaseDependency):
    return image_response(evidence_id, request, database)


@router.get('/{evidence_id}/thumbnail', summary='View the oriented thumbnail')
def thumbnail(evidence_id: UUID, request: Request, database: DatabaseDependency):
    return image_response(evidence_id, request, database, thumbnail=True)
