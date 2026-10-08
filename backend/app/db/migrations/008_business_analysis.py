def upgrade(connection):
    statements = [
        '''CREATE TABLE runtime_models(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
           name VARCHAR(200) NOT NULL, digest VARCHAR(100), status VARCHAR(20) NOT NULL
           CHECK(status IN ('available','missing','unavailable')),checked_at VARCHAR(32) NOT NULL)''',
        '''CREATE TABLE business_analyses(id VARCHAR(36) NOT NULL PRIMARY KEY,
           run_id VARCHAR(36) NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
           input_hash VARCHAR(64) NOT NULL, result JSON NOT NULL CHECK(json_valid(result)),
           cache_payload JSON NOT NULL CHECK(json_valid(cache_payload)),
           provenance JSON NOT NULL CHECK(json_valid(provenance)),created_at VARCHAR(32) NOT NULL)''',
        'CREATE INDEX ix_business_analyses_input_hash ON business_analyses(input_hash)',
        '''CREATE TABLE model_diagnostics(id VARCHAR(36) NOT NULL PRIMARY KEY,
           lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
           artifact_key VARCHAR(200) NOT NULL,expires_at VARCHAR(32) NOT NULL)''',
        'CREATE INDEX ix_model_diagnostics_lead_id ON model_diagnostics(lead_id)',
        '''CREATE TRIGGER business_analyses_no_update BEFORE UPDATE ON business_analyses
           BEGIN SELECT RAISE(ABORT,'Business analysis is immutable'); END''',
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
