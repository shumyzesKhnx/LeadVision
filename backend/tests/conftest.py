from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.foundation.config import Settings
from app.modules.foundation.migration_runner import migrate
from app.modules.foundation.database_session import Database
from app.main import create_app
from app.modules.foundation.common_schema import DependencyHealth


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / "data", embedding_model_dir=tmp_path / 'models', sqlite_busy_timeout_ms=20)


@pytest.fixture
def database(settings):
    settings.data_dir.mkdir()
    db = Database(settings)
    migrate(db.engine)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def application(settings, monkeypatch):
    from app.modules.processing.workflow_service import StageFailure
    def offline_destination(url): raise StageFailure('DNS_FAILURE')
    monkeypatch.setattr('app.modules.evidence.safe_http_client.destination', offline_destination)
    monkeypatch.setattr('app.modules.nlp.model_cache_service.model_info', lambda settings: {'status': 'missing', 'digest': None})
    async def offline_probe(_url):
        return DependencyHealth(status="unavailable", message="Ollama is unavailable.")

    monkeypatch.setattr("app.modules.foundation.health_api.probe_ollama", offline_probe)
    return create_app(settings)


@pytest.fixture
def client(application):
    with TestClient(application, base_url="http://127.0.0.1:8000") as value:
        yield value
