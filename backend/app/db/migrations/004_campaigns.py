"""Create campaigns and preserve activity/cleanup links while adding campaign FK."""

from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    statements = [
        'CREATE UNIQUE INDEX ux_icps_agency_id_id ON icps (agency_id,id)',
        '''CREATE TABLE campaigns (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
            icp_id VARCHAR(36) NOT NULL,
            name VARCHAR(200) NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
            description TEXT,
            archived BOOLEAN NOT NULL CHECK (archived IN (0,1)),
            revision INTEGER NOT NULL CHECK (revision >= 1),
            created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL,
            FOREIGN KEY (agency_id,icp_id) REFERENCES icps(agency_id,id) ON DELETE RESTRICT
        )''',
        'CREATE INDEX ix_campaigns_agency_id ON campaigns (agency_id)',
        'CREATE INDEX ix_campaigns_icp_id ON campaigns (icp_id)',
        '''CREATE TABLE activities_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) REFERENCES agencies(id) ON DELETE RESTRICT,
            campaign_id VARCHAR(36) REFERENCES campaigns(id) ON DELETE RESTRICT,
            lead_id VARCHAR(36), action VARCHAR(100) NOT NULL, origin VARCHAR(20) NOT NULL,
            actor_label VARCHAR(200), old_value JSON, new_value JSON,
            event_key TEXT UNIQUE, created_at VARCHAR(32) NOT NULL,
            CONSTRAINT ck_activity_origin CHECK (origin IN ('operator','api','worker','import','n8n'))
        )''',
        'INSERT INTO activities_new SELECT * FROM activities',
        '''CREATE TABLE file_cleanup_tasks_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY, artifact_key TEXT NOT NULL,
            reason VARCHAR(200) NOT NULL, state VARCHAR(20) NOT NULL,
            attempts INTEGER NOT NULL CHECK (attempts >= 0), last_error VARCHAR(100),
            created_at VARCHAR(32) NOT NULL, completed_at VARCHAR(32),
            activity_id VARCHAR(36) REFERENCES activities_new(id) ON DELETE SET NULL,
            CONSTRAINT ck_cleanup_state CHECK (state IN ('pending','completed','failed'))
        )''',
        'INSERT INTO file_cleanup_tasks_new SELECT * FROM file_cleanup_tasks',
        'DROP TABLE file_cleanup_tasks',
        'DROP TABLE activities',
        'ALTER TABLE activities_new RENAME TO activities',
        'ALTER TABLE file_cleanup_tasks_new RENAME TO file_cleanup_tasks',
        'CREATE INDEX ix_activities_lead_id ON activities (lead_id)',
        'CREATE INDEX ix_activities_campaign_id ON activities (campaign_id)',
        'CREATE INDEX ix_file_cleanup_tasks_state ON file_cleanup_tasks (state)',
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
        raise RuntimeError('Campaign migration foreign key check failed.')
