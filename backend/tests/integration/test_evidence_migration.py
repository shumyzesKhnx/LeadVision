import importlib
import pytest
from sqlalchemy import inspect, insert
from app.core.hashing import content_hash
from app.db.base import SchemaVersion
from app.db.session import Database
from app.db.migration_runner import MIGRATIONS_DIR, migrate, SUPPORTED_SCHEMA_VERSION


@pytest.mark.parametrize('broken', [False, True])
def test_schema_six_upgrade_preserves_existing_rows_and_rolls_back(settings, monkeypatch, broken):
    settings.data_dir.mkdir()
    database = Database(settings)
    try:
        with database.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            for source in sorted(MIGRATIONS_DIR.glob('00[1-6]_*.py')):
                importlib.import_module('app.db.migrations.' + source.stem).upgrade(connection)
                connection.execute(insert(SchemaVersion).values(version=int(source.name[:3]),
                    checksum=content_hash(source.read_text(encoding='utf-8').encode()), applied_at='time'))
            connection.exec_driver_sql("INSERT INTO activities(id,action,origin,created_at) VALUES('preserved','legacy','api','time')")
        if broken:
            module = importlib.import_module('app.db.migrations.007_evidence')
            original = module.upgrade
            def fail(connection):
                original(connection)
                raise RuntimeError('Injected migration failure')
            monkeypatch.setattr(module, 'upgrade', fail)
            with pytest.raises(RuntimeError):
                migrate(database.engine)
            assert 'evidence' not in inspect(database.engine).get_table_names()
        else:
            assert migrate(database.engine) == SUPPORTED_SCHEMA_VERSION
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT id FROM activities').scalar() == 'preserved'
            assert connection.exec_driver_sql('SELECT max(version) FROM schema_versions').scalar() == (6 if broken else SUPPORTED_SCHEMA_VERSION)
            assert not connection.exec_driver_sql('PRAGMA foreign_key_check').all()
    finally:
        database.close()
