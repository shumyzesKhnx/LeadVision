"""Consistent public errors; never serialize raw exceptions or request input."""

import logging
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger("leadvision.errors")


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 409,
        details: list[ErrorDetail] | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def error_response(request: Request, error: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    body = ErrorResponse(
        error=ErrorBody(
            code=error.code,
            message=error.message,
            details=error.details[:30],
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=error.status_code,
        content=body.model_dump(exclude_none=True),
        headers={"X-Request-ID": request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError):
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        reasons = {
            "missing": "Field is required.",
            "extra_forbidden": "Unknown field.",
            "json_invalid": "Invalid JSON.",
            "int_parsing": "Enter a whole number.",
            "int_type": "Enter a whole number.",
            "string_too_long": "Text exceeds its length limit.",
            "greater_than_equal": "Value is below its minimum.",
            "less_than_equal": "Value exceeds its maximum.",
        }
        details = [
            ErrorDetail(
                field=".".join(str(part) for part in item["loc"])[:200],
                reason=reasons.get(item["type"], "Invalid value."),
            )
            for item in exc.errors()[:30]
        ]
        return error_response(
            request, AppError("VALIDATION_ERROR", "Check the highlighted fields.", 422, details)
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        known = {
            404: ("NOT_FOUND", "Resource not found."),
            405: ("METHOD_NOT_ALLOWED", "This method is not available for this resource."),
            413: ("PAYLOAD_TOO_LARGE", "The request exceeds its size limit."),
        }
        code, message = known.get(exc.status_code, ("HTTP_ERROR", "The request could not complete."))
        response = error_response(request, AppError(code, message, exc.status_code))
        if exc.headers and "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("Database failure (%s), request_id=%s", type(exc).__name__, request.state.request_id)
        if isinstance(exc, OperationalError):
            code = getattr(exc.orig, "sqlite_errorcode", 0) or 0
            busy = (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
            return error_response(
                request,
                AppError(
                    "DATABASE_BUSY" if busy else "DATABASE_UNAVAILABLE",
                    "The database is busy. Try again." if busy else "The database is unavailable.",
                    503,
                    [ErrorDetail(reason="Retry after checking database readiness.", retryable=True)],
                ),
            )
        return error_response(request, AppError("INTERNAL_ERROR", "The request could not complete.", 500))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        # Logging the raw exception can reveal credentials embedded in user input.
        logger.error("Internal failure (%s), request_id=%s", type(exc).__name__, request.state.request_id)
        return error_response(request, AppError("INTERNAL_ERROR", "The request could not complete.", 500))
