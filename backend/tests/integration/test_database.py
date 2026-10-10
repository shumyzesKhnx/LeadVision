import importlib
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.modules.foundation.config import Settings
from app.modules.foundation.storage import ArtifactStorage
from app.modules.foundation.database_base import SchemaVersion
from app.modules.foundation.migration_runner import migrate, SUPPORTED_SCHEMA_VERSION
from app.modules.foundation.database_session import Database
from app.modules.processing.activity_model import Activity
from app.modules.foundation.maintenance_model import FileCleanupTask
from app.modules.processing.activity_service import record_activity
from app.modules.foundation.file_cleanup_service import perform_cleanup, queue_cleanup


def test_restart_and_repeat_migration_preserve_committed_records(database, settings):
    with database.transaction() as session:
        event = record_activity(session, action="test.created", origin="api")
        event_id = event.id
    assert migrate(database.engine) == SUPPORTED_SCHEMA_VERSION
    database.close()
    reopened = Database(settings)
    try:
        migrate(reopened.engine)
        with reopened.sessions() as session:
            assert session.get(Activity, event_id).action == "test.created"
            assert session.scalar(select(func.count()).select_from(SchemaVersion)) == SUPPORTED_SCHEMA_VERSION
    finally:
        reopened.close()


def test_failed_transaction_preserves_earlier_commit(database):
    with database.transaction() as session:
        record_activity(session, action="committed", origin="api")
    with pytest.raises(RuntimeError), database.transaction() as session:
        record_activity(session, action="rolled_back", origin="api")
        raise RuntimeError("Abort")
    with database.sessions() as session:
        assert list(session.scalars(select(Activity.action))) == ["committed"]


def test_foreign_keys_wal_and_timeout_on_independent_connections(database, settings):
    with database.engine.connect() as first, database.engine.connect() as second:
        for connection in (first, second):
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
            assert connection.scalar(text("PRAGMA busy_timeout")) == settings.sqlite_busy_timeout_ms
    with pytest.raises(IntegrityError), database.transaction() as session:
        session.add(FileCleanupTask(artifact_key="evidence/test.txt", reason="test", activity_id="missing"))
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(FileCleanupTask)) == 0


def test_activity_retries_do_not_duplicate_events(database):
    with database.transaction() as session:
        first = record_activity(session, action="stage.saved", origin="worker", event_key="job:1:text")
        second = record_activity(session, action="stage.saved", origin="worker", event_key="job:1:text")
        assert first.id == second.id
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Activity)) == 1


def test_sensitive_activity_keys_are_rejected(database):
    with pytest.raises(ValueError), database.transaction() as session:
        record_activity(session, action="unsafe", origin="api", new_value={"nested": {"api_key": "secret"}})


def test_changed_applied_migration_is_rejected(database, tmp_path, monkeypatch):
    from app.modules.foundation import migration_runner

    source = migration_runner.MIGRATIONS_DIR / "001_foundation.py"
    copied = tmp_path / source.name
    for path in migration_runner.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.py"):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    copied.write_bytes(source.read_bytes() + b"\n# changed\n")
    monkeypatch.setattr(migration_runner, "MIGRATIONS_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="migration changed"):
        migrate(database.engine)


def test_newer_schema_is_rejected(database):
    with database.transaction() as session:
        session.add(SchemaVersion(version=SUPPORTED_SCHEMA_VERSION + 1, checksum="f" * 64, applied_at="2026-10-07T00:00:00Z"))
    with pytest.raises(RuntimeError, match="newer"):
        migrate(database.engine)


def test_git_line_ending_changes_do_not_invalidate_migration(database, tmp_path, monkeypatch):
    from app.modules.foundation import migration_runner

    for source in migration_runner.MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.py"):
        (tmp_path / source.name).write_bytes(source.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(migration_runner, "MIGRATIONS_DIR", tmp_path)
    assert migrate(database.engine) == SUPPORTED_SCHEMA_VERSION


def test_migration_failure_rolls_back_ddl(settings, monkeypatch):
    settings.data_dir.mkdir()
    database = Database(settings)
    module = importlib.import_module("app.modules.foundation.001_foundation")

    def broken(connection):
        connection.exec_driver_sql("CREATE TABLE temporary_table (id INTEGER)")
        raise RuntimeError("Simulated migration failure")

    monkeypatch.setattr(module, "upgrade", broken)
    try:
        with pytest.raises(RuntimeError):
            migrate(database.engine)
        assert inspect(database.engine).get_table_names() == []
    finally:
        database.close()


def test_existing_database_mode_does_not_create_a_replacement(settings):
    settings.database_must_exist = True
    with pytest.raises(RuntimeError, match="missing"):
        Database(settings)
    assert not settings.database_path.exists()


def test_existing_empty_database_is_not_silently_initialized(settings):
    settings.data_dir.mkdir()
    settings.database_path.touch()
    settings.database_must_exist = True
    database = Database(settings)
    try:
        with pytest.raises(RuntimeError, match="not initialized"):
            migrate(database.engine, require_initialized=True)
    finally:
        database.close()


def test_cleanup_only_happens_after_business_commit(database, settings):
    storage = ArtifactStorage(settings.data_dir)
    key = storage.write(b"owned", category="evidence", suffix=".txt", max_bytes=5)
    with database.transaction() as session:
        task = queue_cleanup(session, storage, artifact_key=key, reason="lead deletion")
        task_id = task.id
        assert storage.resolve(key).exists()
    with database.transaction() as session:
        perform_cleanup(session, storage, task_id)
    assert not storage.resolve(key).exists()
    with database.sessions() as session:
        assert session.get(FileCleanupTask, task_id).state == "completed"


def test_failed_cleanup_is_retryable_and_keeps_safe_error(database, settings, monkeypatch):
    storage = ArtifactStorage(settings.data_dir)
    key = storage.write(b"owned", category="evidence", suffix=".txt", max_bytes=5)
    with database.transaction() as session:
        task_id = queue_cleanup(session, storage, artifact_key=key, reason="test").id
    original = storage.delete

    def failure(_key):
        raise PermissionError("C:/private/credentials")

    monkeypatch.setattr(storage, "delete", failure)
    with database.transaction() as session:
        perform_cleanup(session, storage, task_id)
    with database.sessions() as session:
        task = session.get(FileCleanupTask, task_id)
        assert task.state == "failed"
        assert task.last_error == "FILE_CLEANUP_FAILED"
    monkeypatch.setattr(storage, "delete", original)
    with database.transaction() as session:
        perform_cleanup(session, storage, task_id)
    with database.sessions() as session:
        assert session.get(FileCleanupTask, task_id).attempts == 2


def test_competing_write_is_bounded_by_busy_timeout(database):
    with database.engine.connect().execution_options(sqlite_begin_mode="IMMEDIATE") as owner:
        with owner.begin():
            with pytest.raises(OperationalError), database.transaction() as session:
                record_activity(session, action="blocked", origin="api")
