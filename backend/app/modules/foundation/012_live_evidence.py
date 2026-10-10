"""Rebuild evidence with FKs temporarily disabled by the migration runner only."""
def upgrade(connection):
    connection.exec_driver_sql('''CREATE TABLE evidence_new (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        run_id VARCHAR(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
        saved_upload_id VARCHAR(36) REFERENCES saved_evidence_uploads(id) ON DELETE CASCADE,
        kind VARCHAR(10) NOT NULL CHECK(kind IN ('text','image')),
        source_mode VARCHAR(20) NOT NULL CHECK(source_mode IN ('cached','uploaded','live')),
        original_url VARCHAR(2048), collected_at VARCHAR(32), imported_at VARCHAR(32) NOT NULL,
        metadata_json JSON NOT NULL CHECK(json_valid(metadata_json)),
        usable BOOLEAN NOT NULL CHECK(usable IN (0,1)), review_reason VARCHAR(500),
        revision INTEGER NOT NULL CHECK(revision>=1), updated_at VARCHAR(32) NOT NULL,
        UNIQUE(run_id,kind), CHECK(usable=1 OR length(trim(review_reason))>=3),
        CHECK(source_mode='live' OR saved_upload_id IS NOT NULL))''')
    connection.exec_driver_sql('INSERT INTO evidence_new SELECT * FROM evidence')
    connection.exec_driver_sql('DROP TABLE evidence')
    connection.exec_driver_sql('ALTER TABLE evidence_new RENAME TO evidence')
    connection.exec_driver_sql('CREATE INDEX ix_evidence_run_id ON evidence(run_id)')
    connection.exec_driver_sql('''CREATE TRIGGER evidence_source_no_update BEFORE UPDATE OF id,run_id,saved_upload_id,kind,
        source_mode,original_url,collected_at,imported_at,metadata_json ON evidence
        BEGIN SELECT RAISE(ABORT,'Evidence source is immutable'); END''')
    connection.exec_driver_sql('''CREATE TABLE live_artifacts (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        run_id VARCHAR(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
        lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        kind VARCHAR(10) NOT NULL CHECK(kind IN ('text','image')),
        state VARCHAR(20) NOT NULL CHECK(state IN ('staging','ready','attached','expired')),
        metadata_json JSON NOT NULL CHECK(json_valid(metadata_json)), original_url VARCHAR(2048) NOT NULL,
        collected_at VARCHAR(32) NOT NULL, expires_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('CREATE INDEX ix_live_artifacts_expiry ON live_artifacts(state,expires_at)')
