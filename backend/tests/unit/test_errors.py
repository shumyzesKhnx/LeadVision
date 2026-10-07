import sqlite3

from fastapi.testclient import TestClient
from pydantic import Field
from sqlalchemy.exc import OperationalError

from app.core.errors import AppError
from app.schemas.common import StrictModel


class ExampleInput(StrictModel):
    count: int = Field(ge=0)


def test_validation_identifies_fields_without_echoing_secrets(application, client):
    @application.post("/test-only-validation")
    def validate(body: ExampleInput):
        return body

    response = client.post("/test-only-validation", json={"count": "private-password", "secret": "do-not-print"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert {detail["field"] for detail in response.json()["error"]["details"]} == {"body.count", "body.secret"}
    assert "private-password" not in response.text
    assert "do-not-print" not in response.text
    assert "traceback" not in response.text.lower()


def test_known_error_and_missing_route_use_same_envelope(application, client):
    @application.get("/test-only-conflict")
    def conflict():
        raise AppError("EDIT_CONFLICT", "Reload before saving.")

    for path, status in [("/test-only-conflict", 409), ("/missing", 404)]:
        response = client.get(path)
        assert response.status_code == status
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_unexpected_exception_is_safe_in_response_and_logs(application, caplog):
    @application.get("/test-only-crash")
    def crash():
        raise RuntimeError("C:/private/secret-password token=do-not-print")

    with TestClient(application, base_url="http://127.0.0.1:8000", raise_server_exceptions=False) as client:
        response = client.get("/test-only-crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    for forbidden in ["secret-password", "C:/private", "do-not-print"]:
        assert forbidden not in response.text
        assert forbidden not in caplog.text


def test_database_busy_is_retryable_without_sql_or_paths(application, client):
    @application.get("/test-only-database-busy")
    def busy():
        original = sqlite3.OperationalError("secret database path")
        original.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raise OperationalError("SELECT private_value", {}, original)

    response = client.get("/test-only-database-busy")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_BUSY"
    assert response.json()["error"]["details"][0]["retryable"] is True
    assert "private_value" not in response.text
    assert "secret database" not in response.text
