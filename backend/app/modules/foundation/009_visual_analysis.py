def upgrade(connection):
    connection.exec_driver_sql('''CREATE TABLE visual_analyses(
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        run_id VARCHAR(36) NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
        evidence_id VARCHAR(36) REFERENCES evidence(id) ON DELETE CASCADE,
        input_hash VARCHAR(64) NOT NULL, result JSON NOT NULL CHECK(json_valid(result)),
        provenance JSON NOT NULL CHECK(json_valid(provenance)),created_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('CREATE INDEX ix_visual_analyses_evidence_id ON visual_analyses(evidence_id)')
    connection.exec_driver_sql('CREATE INDEX ix_visual_analyses_input_hash ON visual_analyses(input_hash)')
    connection.exec_driver_sql('''CREATE TRIGGER visual_analyses_no_update BEFORE UPDATE ON visual_analyses
        BEGIN SELECT RAISE(ABORT,'Visual analysis is immutable'); END''')
