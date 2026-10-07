from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.core.hashing import content_hash
from app.db.base import SchemaVersion
from app.db.migration_runner import MIGRATIONS_DIR, migrate
from app.db.session import Database
from app.main import create_app
from app.models.activity import Activity
from app.models.agency import Agency
from app.models.service import Service
from app.services.service_catalog import require_active_service


def add_agency(client):
    response = client.post("/api/v1/agency", json={
        "name": "TechNova", "description": "A digital agency.",
        "contact": {"email": "hello@technova.example", "phone": "+44 123456"},
    })
    assert response.status_code == 201, response.text
    return response


def add_service(client, name="Website redesign", description="We redesign business websites."):
    response = client.post("/api/v1/services", json={"name": name, "description": description})
    assert response.status_code == 201, response.text
    return response


def test_workspace_is_required_before_service_creation(client):
    assert client.get("/api/v1/agency").json()["error"]["code"] == "AGENCY_NOT_FOUND"
    response = client.post("/api/v1/services", json={"name": "SEO", "description": "Search optimization."})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AGENCY_NOT_FOUND"


def test_create_singleton_and_reject_second_agency(client, application):
    first = add_agency(client)
    assert first.headers["etag"] == '"1"'
    assert first.json()["active_service_count"] == 0
    assert client.post("/api/v1/agency", json={"name": "Another"}).status_code == 409
    assert client.get("/api/v1/agency").json()["id"] == first.json()["id"]
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Agency)) == 1
        assert session.scalar(select(func.count()).select_from(Activity)) == 1


@pytest.mark.parametrize("body", [
    {"name": "   "}, {"name": "a" * 201}, {"name": None},
    {"name": "TechNova", "agency_id": "untrusted"},
    {"name": "TechNova", "contact": {"email": "invalid email"}},
    {"name": "TechNova", "contact": {"website": "http://secret:password@example.com"}},
])
def test_invalid_agency_never_creates_a_workspace(client, body):
    response = client.post("/api/v1/agency", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["details"]
    assert client.get("/api/v1/agency").status_code == 404


def test_agency_edits_nulls_and_conflicts(client):
    original = add_agency(client)
    changed = client.patch("/api/v1/agency", headers={"If-Match": original.headers["etag"]}, json={"name": "  TechNova Studio  "})
    assert changed.status_code == 200
    assert changed.json()["name"] == "TechNova Studio"
    assert changed.json()["contact"]["phone"] == "+44 123456"
    assert changed.headers["etag"] == '"2"'
    assert client.patch("/api/v1/agency", headers={"If-Match": '"1"'}, json={"name": "Outdated"}).status_code == 409
    cleared = client.patch("/api/v1/agency", headers={"If-Match": '"2"'}, json={"description": None, "contact": None})
    assert cleared.json()["description"] is None
    assert cleared.json()["contact"] is None
    assert client.patch("/api/v1/agency", headers={"If-Match": '"3"'}, json={"name": None}).status_code == 422


@pytest.mark.parametrize("header,status", [(None, 428), ("1", 422), ('W/"1"', 422), ("*", 422)])
def test_edits_require_exact_quoted_revision(client, header, status):
    add_agency(client)
    headers = {} if header is None else {"If-Match": header}
    response = client.patch("/api/v1/agency", headers=headers, json={"name": "Updated"})
    assert response.status_code == status
    assert client.get("/api/v1/agency").json()["revision"] == 1


def test_noop_does_not_create_an_unnecessary_revision(client, application):
    add_agency(client)
    response = client.patch("/api/v1/agency", headers={"If-Match": '"1"'}, json={"name": "TechNova"})
    assert response.json()["revision"] == 1
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Activity)) == 1


def test_service_deactivation_reactivation_and_active_count(client, application):
    add_agency(client)
    created = add_service(client)
    service_id = created.json()["id"]
    assert created.headers["location"] == f"/api/v1/services/{service_id}"
    assert client.get("/api/v1/agency").json()["active_service_count"] == 1
    inactive = client.patch(f"/api/v1/services/{service_id}", headers={"If-Match": '"1"'}, json={"active": False})
    assert inactive.status_code == 200
    assert inactive.json()["id"] == service_id
    assert inactive.json()["revision"] == 2
    assert client.get("/api/v1/services").json()["total"] == 0
    assert client.get("/api/v1/services?include_inactive=true").json()["total"] == 1
    assert client.get("/api/v1/agency").json()["active_service_count"] == 0
    assert client.get(f"/api/v1/services/{service_id}").json()["active"] is False
    with application.state.database.sessions() as session, pytest.raises(AppError) as error:
        require_active_service(session, service_id)
    assert error.value.code == "NO_ACTIVE_SERVICE"
    active = client.patch(f"/api/v1/services/{service_id}", headers={"If-Match": '"2"'}, json={"active": True})
    assert active.json()["revision"] == 3
    assert client.get("/api/v1/agency").json()["active_service_count"] == 1
    assert client.delete(f"/api/v1/services/{service_id}").status_code == 405
    with application.state.database.sessions() as session:
        actions = list(session.scalars(select(Activity.action).order_by(Activity.created_at)))
        assert actions == ["agency.created", "service.created", "service.deactivated", "service.reactivated"]


@pytest.mark.parametrize("body", [
    {"name": " ", "description": "Offer"}, {"name": "SEO", "description": " "},
    {"name": "SEO"}, {"name": "SEO", "description": "Offer", "agency_id": "other"},
])
def test_bad_services_are_rejected(client, body):
    add_agency(client)
    assert client.post("/api/v1/services", json=body).status_code == 422
    assert client.get("/api/v1/services").json()["total"] == 0


def test_service_edits_and_pagination(client):
    add_agency(client)
    first = add_service(client)
    second = add_service(client, "SEO", "Search optimization.")
    service_id = first.json()["id"]
    changed = client.patch(f"/api/v1/services/{service_id}", headers={"If-Match": '"1"'}, json={"description": "Updated offer."})
    assert changed.json()["description"] == "Updated offer."
    assert changed.json()["revision"] == 2
    assert client.patch(f"/api/v1/services/{service_id}", headers={"If-Match": '"1"'}, json={"name": "Old edit"}).status_code == 409
    pages = [client.get(f"/api/v1/services?page={page}&page_size=1").json() for page in (1, 2)]
    assert all(page["total"] == 2 for page in pages)
    assert {page["items"][0]["id"] for page in pages} == {first.json()["id"], second.json()["id"]}
    assert client.get("/api/v1/services?page_size=101").status_code == 422
    assert client.get(f"/api/v1/services/{uuid4()}").status_code == 404
    for body in [{}, {"description": None}, {"active": None}, {"active": "false"}]:
        assert client.patch(f"/api/v1/services/{service_id}", headers={"If-Match": '"2"'}, json=body).status_code == 422


def test_maximum_valid_descriptions_do_not_overflow_activity_logs(client):
    assert client.post("/api/v1/agency", json={"name": "Long", "description": "λ" * 5000}).status_code == 201
    assert add_service(client, description="λ" * 5000).status_code == 201


def test_records_survive_application_restart(settings, monkeypatch):
    # The application fixture normally provides the offline runtime probe.
    async def unavailable(_url):
        from app.schemas.common import DependencyHealth
        return DependencyHealth(status="unavailable", message="Offline")

    monkeypatch.setattr("app.api.health.probe_ollama", unavailable)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as first:
        agency_id = add_agency(first).json()["id"]
        service_id = add_service(first).json()["id"]
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as second:
        assert second.get("/api/v1/agency").json()["id"] == agency_id
        assert second.get(f"/api/v1/services/{service_id}").json()["name"] == "Website redesign"
        assert second.get("/api/v1/agency").json()["active_service_count"] == 1


def test_activity_failure_rolls_back_workspace(client, application, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Simulated activity failure")

    monkeypatch.setattr("app.services.agency.record_activity", fail)
    assert client.post("/api/v1/agency", json={"name": "Rollback"}).status_code == 500
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Agency)) == 0
        assert session.scalar(select(func.count()).select_from(Activity)) == 0


def test_activity_failure_rolls_back_service_edit(client, application, monkeypatch):
    add_agency(client)
    created = add_service(client)
    def fail(*args, **kwargs):
        raise RuntimeError("Simulated activity failure")

    monkeypatch.setattr("app.services.service_catalog.record_activity", fail)
    assert client.patch(f"/api/v1/services/{created.json()['id']}", headers={"If-Match": '"1"'}, json={"active": False}).status_code == 500
    current = client.get(f"/api/v1/services/{created.json()['id']}").json()
    assert current["active"] is True
    assert current["revision"] == 1
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Activity)) == 2


def test_competing_edits_do_not_overwrite_each_other(settings, application):
    settings.sqlite_busy_timeout_ms = 2000
    with TestClient(application, base_url="http://127.0.0.1:8000") as client:
        add_agency(client)
        gate = Barrier(2)
        def edit(name):
            gate.wait()
            return client.patch("/api/v1/agency", headers={"If-Match": '"1"'}, json={"name": name})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ["Editor A", "Editor B"]))
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(result.json()["name"] for result in results if result.status_code == 200)
        assert client.get("/api/v1/agency").json()["name"] == winner


def test_database_constraints_protect_relationships(database):
    with pytest.raises(IntegrityError), database.transaction() as session:
        session.add(Service(agency_id="missing", name="SEO", description="Offer"))
    with database.transaction() as session:
        session.add(Agency(name="First"))
    with pytest.raises(IntegrityError), database.transaction() as session:
        session.add(Agency(name="Second"))
    with pytest.raises(IntegrityError), database.transaction() as session:
        session.execute(insert(Activity).values(action="test", origin="api", agency_id="missing"))


@pytest.mark.parametrize("orphan_agency", [False, True])
def test_upgrade_preserves_legacy_events_cleanup_links_and_maintenance(settings, orphan_agency):
    settings.data_dir.mkdir()
    database = Database(settings)
    foundation = importlib.import_module("app.db.migrations.001_foundation")
    try:
        with database.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            foundation.upgrade(connection)
            checksum = content_hash((MIGRATIONS_DIR / "001_foundation.py").read_text(encoding="utf-8").encode("utf-8"))
            connection.execute(insert(SchemaVersion).values(version=1, checksum=checksum, applied_at="2026-10-07T00:00:00Z"))
            connection.exec_driver_sql(
                "INSERT INTO activities (id,agency_id,action,origin,created_at) VALUES (?,?,?,?,?)",
                ("event-1", "orphan" if orphan_agency else None, "legacy.event", "api", "2026-10-07T00:00:00Z"),
            )
            connection.exec_driver_sql("INSERT INTO file_cleanup_tasks (id,artifact_key,reason,state,attempts,created_at,activity_id) VALUES ('task-1','evidence/test.txt','legacy','pending',0,'2026-10-07T00:00:00Z','event-1')")
            connection.exec_driver_sql("UPDATE worker_state SET maintenance_requested=1,maintenance_reason='Existing backup'")
        if orphan_agency:
            with pytest.raises(IntegrityError):
                migrate(database.engine)
        else:
            assert migrate(database.engine) == 2
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT action FROM activities WHERE id='event-1'").scalar_one() == "legacy.event"
            assert connection.exec_driver_sql("SELECT activity_id FROM file_cleanup_tasks WHERE id='task-1'").scalar_one() == "event-1"
            assert connection.exec_driver_sql("SELECT maintenance_reason FROM worker_state").scalar_one() == "Existing backup"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").first() is None
            assert connection.exec_driver_sql("SELECT max(version) FROM schema_versions").scalar_one() == (1 if orphan_agency else 2)
    finally:
        database.close()
