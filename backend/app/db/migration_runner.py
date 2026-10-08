"""Apply numbered migrations once, in order, with checksums and rollback."""

import importlib
from pathlib import Path

from sqlalchemy import inspect, insert, select
from sqlalchemy.engine import Engine

from app.core.clock import utc_now
from app.core.hashing import content_hash
from app.db.base import SchemaVersion

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
SUPPORTED_SCHEMA_VERSION = 8


def migrate(engine: Engine, *, require_initialized: bool = False) -> int:
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.py"))
    versions = [int(path.name[:3]) for path in files]
    if versions != list(range(1, SUPPORTED_SCHEMA_VERSION + 1)):
        raise RuntimeError("Migration files are missing or not in consecutive order.")

    with engine.connect().execution_options(sqlite_begin_mode="IMMEDIATE") as connection:
        with connection.begin():
            tables = inspect(connection).get_table_names()
            if require_initialized and "schema_versions" not in tables:
                raise RuntimeError("The existing database is not initialized; migration refused.")
            if tables and "schema_versions" not in tables:
                raise RuntimeError("Unrecognized database; migration refused.")
            SchemaVersion.__table__.create(connection, checkfirst=True)
            applied = dict(
                connection.execute(
                    select(SchemaVersion.version, SchemaVersion.checksum)
                ).all()
            )
            if sorted(applied) != list(range(1, len(applied) + 1)):
                raise RuntimeError("The database migration history is inconsistent.")
            if applied and max(applied) > SUPPORTED_SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this application supports.")

            for path, version in zip(files, versions, strict=True):
                # Git may convert LF/CRLF on Windows; source content, not line endings, is authoritative.
                checksum = content_hash(path.read_text(encoding="utf-8").encode("utf-8"))
                if version in applied:
                    if applied[version] != checksum:
                        raise RuntimeError("An applied migration changed; startup stopped.")
                    continue
                module = importlib.import_module(f"app.db.migrations.{path.stem}")
                module.upgrade(connection)
                connection.execute(
                    insert(SchemaVersion).values(
                        version=version, checksum=checksum, applied_at=utc_now()
                    )
                )
    return SUPPORTED_SCHEMA_VERSION


def main() -> None:
    from app.core.config import Settings
    from app.core.storage import ArtifactStorage, reject_links
    from app.db.session import Database

    settings = Settings()
    ArtifactStorage(settings.data_dir)
    reject_links(settings.database_path)
    database = Database(settings)
    try:
        version = migrate(database.engine, require_initialized=settings.database_must_exist)
        print(f"Database is ready. Schema version: {version}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
