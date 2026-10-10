from fastapi import Request

from app.modules.foundation.database_session import Database


def get_database(request: Request) -> Database:
    return request.app.state.database
