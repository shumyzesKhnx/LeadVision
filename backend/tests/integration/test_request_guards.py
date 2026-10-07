import pytest
from app.db.migration_runner import SUPPORTED_SCHEMA_VERSION

from app.services.maintenance import set_maintenance


def test_health_and_swagger_work_without_models(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == SUPPORTED_SCHEMA_VERSION
    assert body["database"]["status"] == "ready"
    assert body["ollama"]["status"] == "unavailable"
    assert body["worker"]["status"] == "not_implemented"
    assert "data_dir" not in response.text
    assert client.get("/docs").status_code == 200
    assert "/api/v1/health" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("headers,code", [
    ({"Host": "attacker.example"}, "INVALID_HOST"),
    ({"Origin": "https://attacker.example"}, "ORIGIN_NOT_ALLOWED"),
    ({"Origin": "null"}, "ORIGIN_NOT_ALLOWED"),
    ({"Origin": "http://127.0.0.1:9000"}, "ORIGIN_NOT_ALLOWED"),
    ({"Sec-Fetch-Site": "cross-site"}, "ORIGIN_NOT_ALLOWED"),
])
def test_hostile_host_and_origin_are_rejected(client, headers, code):
    response = client.get("/api/v1/health", headers=headers)
    assert response.status_code in {400, 403}
    assert response.json()["error"]["code"] == code
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]


def test_same_origin_and_localhost_alias_are_accepted(client):
    assert client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:8000"}).status_code == 200
    assert client.get("/api/v1/health", headers={"Host": "localhost:8000", "Origin": "http://localhost:8000"}).status_code == 200


def test_request_ids_are_generated_instead_of_trusting_user_input(client):
    first = client.get("/api/v1/health", headers={"X-Request-ID": "untrusted"})
    second = client.get("/api/v1/health")
    assert first.headers["x-request-id"] != "untrusted"
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_maintenance_blocks_writes_but_preserves_read_access(application, client):
    @application.post("/test-only-write")
    def write():
        return {"saved": True}

    assert client.post("/test-only-write").status_code == 200
    with application.state.database.transaction() as session:
        set_maintenance(session, active=True, reason="Backup preparation")
    assert client.post("/test-only-write").json()["error"]["code"] == "MAINTENANCE_ACTIVE"
    assert client.get("/api/v1/health").json()["status"] == "maintenance"
    with application.state.database.transaction() as session:
        set_maintenance(session, active=False)
    assert client.post("/test-only-write").status_code == 200


def test_cross_site_form_post_never_reaches_route(application, client):
    @application.post("/test-only-write")
    def write():
        raise AssertionError("Guard should reject before execution")

    response = client.post("/test-only-write", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_json_preflight_does_not_enable_cross_origin_access(client):
    response = client.options("/api/v1/health", headers={
        "Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"
    })
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers
