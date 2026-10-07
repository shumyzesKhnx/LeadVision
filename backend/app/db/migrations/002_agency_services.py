"""Add agency/services and rebuild activity foreign keys without losing cleanup links."""

from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    statements = [
        """CREATE TABLE agencies (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            singleton_key INTEGER NOT NULL UNIQUE CHECK (singleton_key = 1),
            name VARCHAR(200) NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
            description TEXT, contact JSON,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL
        )""",
        """CREATE TABLE services (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
            name VARCHAR(200) NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
            description TEXT NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 5000),
            active BOOLEAN NOT NULL CHECK (active IN (0,1)),
            revision INTEGER NOT NULL CHECK (revision >= 1),
            created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL
        )""",
        "CREATE INDEX ix_services_agency_id ON services (agency_id)",
        """CREATE TABLE activities_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) REFERENCES agencies(id) ON DELETE RESTRICT,
            campaign_id VARCHAR(36), lead_id VARCHAR(36),
            action VARCHAR(100) NOT NULL, origin VARCHAR(20) NOT NULL,
            actor_label VARCHAR(200), old_value JSON, new_value JSON,
            event_key TEXT UNIQUE, created_at VARCHAR(32) NOT NULL,
            CONSTRAINT ck_activity_origin CHECK (origin IN ('operator','api','worker','import','n8n'))
        )""",
        "INSERT INTO activities_new SELECT * FROM activities",
        """CREATE TABLE file_cleanup_tasks_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY, artifact_key TEXT NOT NULL,
            reason VARCHAR(200) NOT NULL, state VARCHAR(20) NOT NULL,
            attempts INTEGER NOT NULL CHECK (attempts >= 0), last_error VARCHAR(100),
            created_at VARCHAR(32) NOT NULL, completed_at VARCHAR(32),
            activity_id VARCHAR(36) REFERENCES activities_new(id) ON DELETE SET NULL,
            CONSTRAINT ck_cleanup_state CHECK (state IN ('pending','completed','failed'))
        )""",
        "INSERT INTO file_cleanup_tasks_new SELECT * FROM file_cleanup_tasks",
        # Drop dependent old table first so deleting activities cannot clear its links.
        "DROP TABLE file_cleanup_tasks",
        "DROP TABLE activities",
        "ALTER TABLE activities_new RENAME TO activities",
        "ALTER TABLE file_cleanup_tasks_new RENAME TO file_cleanup_tasks",
        "CREATE INDEX ix_activities_lead_id ON activities (lead_id)",
        "CREATE INDEX ix_file_cleanup_tasks_state ON file_cleanup_tasks (state)",
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("Agency migration foreign key check failed.")
