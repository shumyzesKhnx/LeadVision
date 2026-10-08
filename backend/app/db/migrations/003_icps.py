"""Add versioned customer profiles without changing existing workspace data."""

from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    statements = [
        '''CREATE TABLE icps (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
            name VARCHAR(200) NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
            archived BOOLEAN NOT NULL CHECK (archived IN (0,1)),
            revision INTEGER NOT NULL CHECK (revision >= 1), current_version_id VARCHAR(36),
            created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL,
            FOREIGN KEY (id,current_version_id) REFERENCES icp_versions(icp_id,id) ON DELETE RESTRICT
        )''',
        '''CREATE TABLE icp_versions (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            icp_id VARCHAR(36) NOT NULL REFERENCES icps(id) ON DELETE RESTRICT,
            version INTEGER NOT NULL CHECK (version >= 1),
            config JSON NOT NULL CHECK (json_valid(config)),
            score_rule_version VARCHAR(50) NOT NULL,
            content_hash VARCHAR(64) NOT NULL CHECK (length(content_hash)=64),
            semantic_input_hash VARCHAR(64) NOT NULL CHECK (length(semantic_input_hash)=64),
            created_at VARCHAR(32) NOT NULL,
            UNIQUE (icp_id,version), UNIQUE (icp_id,id)
        )''',
        'CREATE INDEX ix_icps_agency_id ON icps (agency_id)',
        'CREATE INDEX ix_icp_versions_icp_id ON icp_versions (icp_id)',
        '''CREATE TRIGGER icp_versions_no_update BEFORE UPDATE ON icp_versions
           BEGIN SELECT RAISE(ABORT, 'ICP versions are immutable'); END''',
        '''CREATE TRIGGER icp_versions_no_delete BEFORE DELETE ON icp_versions
           BEGIN SELECT RAISE(ABORT, 'ICP versions are immutable'); END''',
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
        raise RuntimeError('ICP migration foreign key check failed.')
