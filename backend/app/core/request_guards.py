"""Protect the loopback API from hostile browser origins and Host headers."""

from uuid import uuid4
import logging

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import AppError, error_response
from app.services.maintenance import is_maintenance_active


class RequestGuards:
    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.allowed_hosts = {f"127.0.0.1:{settings.api_port}", f"localhost:{settings.api_port}"}
        self.allowed_origins = settings.allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scope.setdefault("state", {})["request_id"] = str(uuid4())
        request = Request(scope)
        hosts = request.headers.getlist("host")
        origins = request.headers.getlist("origin")
        error = None
        if len(hosts) != 1 or hosts[0].lower() not in self.allowed_hosts:
            error = AppError("INVALID_HOST", "Use the configured local API address.", 400)
        elif len(origins) > 1 or (origins and origins[0] not in self.allowed_origins):
            error = AppError("ORIGIN_NOT_ALLOWED", "This browser origin is not allowed.", 403)
        elif request.headers.get("sec-fetch-site") == "cross-site":
            error = AppError("ORIGIN_NOT_ALLOWED", "Cross-site browser requests are not allowed.", 403)
        elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            # CLI clients have no Origin/Fetch Metadata; browser writes must be same-origin.
            site = request.headers.get("sec-fetch-site")
            if not origins and site is not None and site != "same-origin":
                error = AppError("ORIGIN_NOT_ALLOWED", "Use the same-origin interface.", 403)
            else:
                database = getattr(request.app.state, "database", None)
                if database is not None:
                    try:
                        maintenance = await run_in_threadpool(is_maintenance_active, database)
                    except Exception:
                        error = AppError("DATABASE_UNAVAILABLE", "The database is unavailable.", 503)
                    else:
                        if maintenance:
                            error = AppError("MAINTENANCE_ACTIVE", "Writes are paused for maintenance.", 503)
        if error is not None:
            await error_response(request, error)(scope, receive, send)
            return

        response_started = False

        async def send_with_id(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request.state.request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            # Prevent Uvicorn from logging raw exception strings that may contain secrets.
            logging.getLogger("leadvision.errors").error(
                "Internal failure (%s), request_id=%s", type(exc).__name__, request.state.request_id
            )
            if response_started:
                raise RuntimeError("Response delivery was interrupted.") from None
            await error_response(
                request, AppError("INTERNAL_ERROR", "The request could not complete.", 500)
            )(scope, receive, send)
