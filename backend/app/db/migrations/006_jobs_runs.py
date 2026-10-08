"""Persistent queue, unique active analysis per lead and immutable run inputs."""
from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    statements = [
        '''CREATE TABLE jobs (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
            lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            kind VARCHAR(30) NOT NULL CHECK(kind='analysis'),
            status VARCHAR(20) NOT NULL CHECK(status IN ('queued','running','completed','partial','failed','cancelled')),
            current_stage VARCHAR(50), request_hash VARCHAR(64) NOT NULL,
            request_body JSON NOT NULL CHECK(json_valid(request_body)),
            input_snapshot JSON NOT NULL CHECK(json_valid(input_snapshot)),
            idempotency_key VARCHAR(128) NOT NULL, scope VARCHAR(100) NOT NULL,
            owner_token VARCHAR(36), cancel_requested BOOLEAN NOT NULL CHECK(cancel_requested IN (0,1)),
            retry_of_id VARCHAR(36) REFERENCES jobs(id) ON DELETE SET NULL,
            error JSON, queued_at VARCHAR(32) NOT NULL, started_at VARCHAR(32), finished_at VARCHAR(32),
            UNIQUE(agency_id,scope,idempotency_key)
        )''',
        "CREATE UNIQUE INDEX ux_jobs_active_analysis ON jobs(lead_id) WHERE kind='analysis' AND status IN ('queued','running')",
        'CREATE INDEX ix_jobs_lead_id ON jobs(lead_id)',
        'CREATE INDEX ix_jobs_queue ON jobs(status,queued_at,id)',
        '''CREATE TABLE job_stages (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL, ordinal INTEGER NOT NULL, state VARCHAR(20) NOT NULL
            CHECK(state IN ('pending','running','succeeded','warning','failed','skipped')),
            attempts INTEGER NOT NULL CHECK(attempts BETWEEN 0 AND 2), input_hash VARCHAR(64) NOT NULL,
            output JSON, warnings JSON NOT NULL, error JSON,
            usable BOOLEAN NOT NULL CHECK(usable IN (0,1)), required BOOLEAN NOT NULL CHECK(required IN (0,1)),
            started_at VARCHAR(32), finished_at VARCHAR(32), UNIQUE(job_id,name)
        )''',
        'CREATE INDEX ix_job_stages_job_id ON job_stages(job_id)',
        '''CREATE TABLE analysis_runs (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
            lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            icp_version_id VARCHAR(36) NOT NULL REFERENCES icp_versions(id) ON DELETE RESTRICT,
            lead_input_revision INTEGER NOT NULL CHECK(lead_input_revision>=1),
            evidence_mode VARCHAR(20) NOT NULL CHECK(evidence_mode IN ('live','cached','uploaded')),
            input_snapshot JSON NOT NULL CHECK(json_valid(input_snapshot)),
            fingerprint VARCHAR(64) NOT NULL, created_at VARCHAR(32) NOT NULL
        )''',
        'CREATE INDEX ix_analysis_runs_lead_id ON analysis_runs(lead_id)',
        '''CREATE TRIGGER analysis_runs_no_update BEFORE UPDATE ON analysis_runs
           BEGIN SELECT RAISE(ABORT,'Analysis run inputs are immutable'); END''',
        '''CREATE TRIGGER jobs_inputs_no_update BEFORE UPDATE OF agency_id,lead_id,kind,request_hash,request_body,
            input_snapshot,idempotency_key,scope,queued_at ON jobs
           BEGIN SELECT RAISE(ABORT,'Job inputs are immutable'); END''',
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
        raise RuntimeError('Job migration foreign key check failed.')
