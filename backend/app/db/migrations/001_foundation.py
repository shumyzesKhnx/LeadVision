"""Create the foundation. Never edit this file after its migration is applied."""

from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    # Freeze the original DDL here; later ORM changes must not alter migration 001.
    statements = [
        """CREATE TABLE activities (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36), campaign_id VARCHAR(36), lead_id VARCHAR(36),
            action VARCHAR(100) NOT NULL, origin VARCHAR(20) NOT NULL,
            actor_label VARCHAR(200), old_value JSON, new_value JSON,
            event_key TEXT UNIQUE, created_at VARCHAR(32) NOT NULL,
            CONSTRAINT ck_activity_origin CHECK (origin IN ('operator','api','worker','import','n8n'))
        )""",
        "CREATE INDEX ix_activities_lead_id ON activities (lead_id)",
        """CREATE TABLE worker_state (
            singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
            owner_token VARCHAR(36), heartbeat VARCHAR(32), process_start_identity VARCHAR(100),
            maintenance_requested BOOLEAN NOT NULL CHECK (maintenance_requested IN (0,1)),
            worker_paused BOOLEAN NOT NULL CHECK (worker_paused IN (0,1)),
            maintenance_reason VARCHAR(500)
        )""",
        """CREATE TABLE file_cleanup_tasks (
            id VARCHAR(36) NOT NULL PRIMARY KEY, artifact_key TEXT NOT NULL,
            reason VARCHAR(200) NOT NULL, state VARCHAR(20) NOT NULL,
            attempts INTEGER NOT NULL CHECK (attempts >= 0), last_error VARCHAR(100),
            created_at VARCHAR(32) NOT NULL, completed_at VARCHAR(32),
            activity_id VARCHAR(36) REFERENCES activities(id) ON DELETE SET NULL,
            CONSTRAINT ck_cleanup_state CHECK (state IN ('pending','completed','failed'))
        )""",
        "CREATE INDEX ix_file_cleanup_tasks_state ON file_cleanup_tasks (state)",
        "INSERT INTO worker_state (singleton,maintenance_requested,worker_paused) VALUES (1,0,0)",
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
