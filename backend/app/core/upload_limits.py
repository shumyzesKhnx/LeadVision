"""Bound multipart request size before the framework spools an entire CSV upload."""

from fastapi import Request
from fastapi import HTTPException
from app.core.errors import AppError, error_response

MAX_IMPORT_REQUEST_BYTES = 5_000_000 + 65_536  # File limit plus bounded multipart overhead.
MAX_EVIDENCE_REQUEST_BYTES = 11_000_000 + 65_536


class ImportUploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        importing = scope['path'].startswith('/api/v1/campaigns/') and scope['path'].endswith('/imports')
        evidence = scope['path'].startswith('/api/v1/leads/') and scope['path'].endswith('/saved-evidence')
        if not (importing or evidence):
            return await self.app(scope, receive, send)
        limit = MAX_IMPORT_REQUEST_BYTES if importing else MAX_EVIDENCE_REQUEST_BYTES
        code = 'CSV_TOO_LARGE' if importing else 'EVIDENCE_TOO_LARGE'
        message = 'CSV files must be at most 5 MB.' if importing else 'Saved evidence requests exceed their size limit.'
        request = Request(scope)
        length = request.headers.get('content-length')
        if length is not None:
            try:
                count = int(length)
                if count < 0:
                    raise ValueError('Negative content length')
                too_large = count > limit
            except ValueError:
                return await error_response(request, AppError('INVALID_CONTENT_LENGTH', 'Invalid request size.', 400))(scope, receive, send)
            if too_large:
                return await error_response(request, AppError(code, message, 413))(scope, receive, send)
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            if received > limit:
                # FastAPI preserves HTTPException while parsing multipart bodies.
                raise HTTPException(status_code=413)
            return message
        await self.app(scope, bounded_receive, send)
