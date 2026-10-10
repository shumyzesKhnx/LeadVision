import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.foundation.clock import to_karachi, utc_now
from app.modules.foundation.config import PROJECT_ROOT, Settings
from app.modules.foundation.hashing import content_hash, snapshot_hash


def test_configuration_has_stable_project_relative_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert PROJECT_ROOT == Path(__file__).resolve().parents[3]
    assert Settings(_env_file=None).data_dir == PROJECT_ROOT / "data"


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("LEADVISION_API_PORT", "8012")
    settings = Settings(_env_file=None)
    assert settings.api_port == 8012
    assert "http://localhost:8012" in settings.allowed_origins


@pytest.mark.parametrize("name", ["../private.sqlite3", "C:\\private.sqlite3", "sub/a.sqlite3", "", "file.db"])
def test_database_name_cannot_choose_an_arbitrary_path(name):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_name=name)


@pytest.mark.parametrize("url", ["https://example.com", "http://10.0.0.1:11434", "http://secret:password@localhost:11434", "http://localhost:11434/path"])
def test_runtime_is_loopback_without_credentials(url):
    with pytest.raises(ValidationError) as failure:
        Settings(_env_file=None, ollama_base_url=url)
    assert url not in str(failure.value)


def test_public_binding_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, api_host="0.0.0.0")


def test_clock_conversion_and_naive_timestamp_rejection():
    assert utc_now().endswith("Z")
    assert to_karachi("2026-10-07T15:00:00Z") == "2026-10-07T20:00:00+05:00"
    with pytest.raises(ValueError):
        to_karachi("2026-10-07T15:00:00")


def test_hashes_are_stable_and_reject_nonfinite_inputs():
    assert snapshot_hash({"a": 1, "b": 2}) == snapshot_hash({"b": 2, "a": 1})
    assert content_hash(b"hello") != content_hash(b"Hello")
    with pytest.raises(ValueError):
        snapshot_hash({"value": math.nan})
