def upgrade(connection):
    connection.exec_driver_sql('''CREATE TABLE embedding_runtime(
        id INTEGER PRIMARY KEY CHECK(id=1),status VARCHAR(20) NOT NULL,
        identity JSON NOT NULL CHECK(json_valid(identity)),checked_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('''CREATE TABLE embeddings(
        id VARCHAR(36) PRIMARY KEY NOT NULL,agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
        purpose VARCHAR(20) NOT NULL CHECK(purpose IN ('company','icp','knowledge')),
        input_hash VARCHAR(64) NOT NULL,space_hash VARCHAR(64) NOT NULL,
        dimensions INTEGER NOT NULL CHECK(dimensions=384),vector BLOB NOT NULL CHECK(length(vector)=1536),
        metadata_json JSON NOT NULL CHECK(json_valid(metadata_json)),created_at VARCHAR(32) NOT NULL,
        UNIQUE(agency_id,purpose,input_hash,space_hash))''')
    connection.exec_driver_sql('''CREATE TABLE embedding_leads(
        embedding_id VARCHAR(36) NOT NULL REFERENCES embeddings(id) ON DELETE CASCADE,
        lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        PRIMARY KEY(embedding_id,lead_id))''')
    connection.exec_driver_sql('''CREATE TABLE semantic_results(
        id VARCHAR(36) PRIMARY KEY NOT NULL,run_id VARCHAR(36) NOT NULL UNIQUE REFERENCES analysis_runs(id) ON DELETE CASCADE,
        company_embedding_id VARCHAR(36) REFERENCES embeddings(id),icp_embedding_id VARCHAR(36) REFERENCES embeddings(id),
        result JSON NOT NULL CHECK(json_valid(result)),provenance JSON NOT NULL CHECK(json_valid(provenance)),
        created_at VARCHAR(32) NOT NULL)''')
    for table in ('embeddings', 'semantic_results'):
        connection.exec_driver_sql(f'''CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
            BEGIN SELECT RAISE(ABORT,'Embedding/semantic results are immutable'); END''')
