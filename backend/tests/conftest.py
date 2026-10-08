from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.db.migration_runner import migrate
from app.db.session import Database
from app.main import create_app
from app.schemas.common import DependencyHealth


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path / "data", sqlite_busy_timeout_ms=20)


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
    monkeypatch.setattr('app.services.model_cache.model_info', lambda settings: {'status': 'missing', 'digest': None})
    async def offline_probe(_url):
        return DependencyHealth(status="unavailable", message="Ollama is unavailable.")

    monkeypatch.setattr("app.api.health.probe_ollama", offline_probe)
    return create_app(settings)


@pytest.fixture
def client(application):
    with TestClient(application, base_url="http://127.0.0.1:8000") as value:
        yield value
