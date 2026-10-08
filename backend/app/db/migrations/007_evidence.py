"""Durable saved uploads and immutable evidence provenance with editable review."""
from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    statements = [
        '''CREATE TABLE saved_evidence_uploads (
           id VARCHAR(36) NOT NULL PRIMARY KEY,
           lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
           token_hash VARCHAR(64) NOT NULL UNIQUE,
           source_mode VARCHAR(20) NOT NULL CHECK(source_mode IN ('cached','uploaded')),
           state VARCHAR(20) NOT NULL CHECK(state IN ('staging','ready','attached','expired')),
           manifest JSON NOT NULL CHECK(json_valid(manifest)),
           attached_job_id VARCHAR(36) REFERENCES jobs(id) ON DELETE SET NULL,
           imported_at VARCHAR(32) NOT NULL, expires_at VARCHAR(32) NOT NULL
        )''',
        'CREATE INDEX ix_saved_evidence_uploads_lead_id ON saved_evidence_uploads(lead_id)',
        'CREATE INDEX ix_saved_evidence_uploads_expiry ON saved_evidence_uploads(state,expires_at)',
        '''CREATE TABLE evidence (
           id VARCHAR(36) NOT NULL PRIMARY KEY,
           run_id VARCHAR(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
           saved_upload_id VARCHAR(36) NOT NULL REFERENCES saved_evidence_uploads(id) ON DELETE CASCADE,
           kind VARCHAR(10) NOT NULL CHECK(kind IN ('text','image')),
           source_mode VARCHAR(20) NOT NULL CHECK(source_mode IN ('cached','uploaded')),
           original_url VARCHAR(2048), collected_at VARCHAR(32), imported_at VARCHAR(32) NOT NULL,
           metadata_json JSON NOT NULL CHECK(json_valid(metadata_json)),
           usable BOOLEAN NOT NULL CHECK(usable IN (0,1)), review_reason VARCHAR(500),
           revision INTEGER NOT NULL CHECK(revision>=1), updated_at VARCHAR(32) NOT NULL,
           UNIQUE(run_id,kind), CHECK(usable=1 OR length(trim(review_reason))>=3)
        )''',
        'CREATE INDEX ix_evidence_run_id ON evidence(run_id)',
        '''CREATE TRIGGER evidence_source_no_update BEFORE UPDATE OF id,run_id,saved_upload_id,kind,
           source_mode,original_url,collected_at,imported_at,metadata_json ON evidence
           BEGIN SELECT RAISE(ABORT,'Evidence source is immutable'); END''',
        '''CREATE TRIGGER saved_evidence_ready_no_update BEFORE UPDATE OF lead_id,token_hash,source_mode,
           manifest,imported_at,expires_at ON saved_evidence_uploads WHEN OLD.state!='staging'
           BEGIN SELECT RAISE(ABORT,'Ready upload source is immutable'); END''',
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
        raise RuntimeError('Evidence migration foreign key check failed.')
