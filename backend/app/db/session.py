"""Short transactions with SQLite protections on every connection."""

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings):
        if settings.database_must_exist and not settings.database_path.is_file():
            raise RuntimeError("The configured existing database is missing; startup stopped.")
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(settings.database_path)),
            connect_args={"check_same_thread": False},
            hide_parameters=True,
        )

        @event.listens_for(self.engine, "connect")
        def set_connection_options(connection, _record):
            # Manage BEGIN explicitly so DDL/migrations really roll back on SQLite.
            connection.isolation_level = None
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
                cursor.execute("PRAGMA journal_mode=WAL")
                if cursor.fetchone()[0].lower() != "wal":
                    raise RuntimeError("SQLite could not enable WAL mode.")
            finally:
                cursor.close()

        @event.listens_for(self.engine, "begin")
        def begin_transaction(connection):
            mode = connection.get_execution_options().get("sqlite_begin_mode", "DEFERRED")
            if mode not in {"DEFERRED", "IMMEDIATE"}:
                raise ValueError("Unsupported SQLite transaction mode.")
            connection.exec_driver_sql(f"BEGIN {mode}")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[Session]:
        """Commit all changes together, or roll them back on any exception."""
        with self.sessions() as session, session.begin():
            if immediate:
                # Serialize short read-modify-write operations before reading revision.
                session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
            yield session

    def close(self) -> None:
        self.engine.dispose()
