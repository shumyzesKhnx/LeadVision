def upgrade(connection):
    connection.exec_driver_sql('''CREATE TABLE score_runs(
        id VARCHAR(36) NOT NULL PRIMARY KEY,run_id VARCHAR(36) NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
        lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        result JSON NOT NULL CHECK(json_valid(result)),provenance JSON NOT NULL CHECK(json_valid(provenance)),
        created_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('CREATE INDEX ix_score_runs_lead_id ON score_runs(lead_id)')
    connection.exec_driver_sql('''CREATE TABLE score_components(
        id VARCHAR(36) NOT NULL PRIMARY KEY,score_id VARCHAR(36) NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE,
        name VARCHAR(20) NOT NULL,result JSON NOT NULL CHECK(json_valid(result)),UNIQUE(score_id,name))''')
    connection.exec_driver_sql('''CREATE TABLE reviewer_overrides(
        id VARCHAR(36) NOT NULL PRIMARY KEY,lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        score_id VARCHAR(36) NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE,
        kind VARCHAR(20) NOT NULL CHECK(kind IN ('priority','exclusion','qualification')),
        value VARCHAR(20) NOT NULL,reason VARCHAR(1000) NOT NULL CHECK(length(trim(reason))>=3),
        reviewer VARCHAR(100) NOT NULL CHECK(length(trim(reviewer))>=1),
        binding JSON NOT NULL CHECK(json_valid(binding)),created_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('CREATE INDEX ix_reviewer_overrides_lead_id ON reviewer_overrides(lead_id)')
    for table in ('score_runs', 'score_components', 'reviewer_overrides'):
        connection.exec_driver_sql(f'''CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
            BEGIN SELECT RAISE(ABORT,'Calculated scores and reviewer history are immutable'); END''')
