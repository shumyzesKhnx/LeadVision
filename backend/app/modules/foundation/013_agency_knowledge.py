"""Versioned agency facts and indexes; preserve the existing analysis queue."""


def upgrade(connection):
    ddl = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").scalar_one()
    if "CHECK(kind='analysis')" not in ddl or 'lead_id VARCHAR(36) NOT NULL' not in ddl:
        raise RuntimeError('Unexpected queue schema; migration refused.')
    dependents = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE tbl_name='jobs' AND type IN ('index','trigger') AND sql IS NOT NULL").scalars().all()
    ddl = ddl.replace('CREATE TABLE jobs', 'CREATE TABLE jobs_new', 1)
    ddl = ddl.replace('lead_id VARCHAR(36) NOT NULL', 'lead_id VARCHAR(36)', 1)
    ddl = ddl.replace("CHECK(kind='analysis')", "CHECK(kind IN ('analysis','knowledge_index')) CHECK((kind='analysis' AND lead_id IS NOT NULL) OR (kind='knowledge_index' AND lead_id IS NULL))", 1)
    connection.exec_driver_sql(ddl)
    connection.exec_driver_sql('INSERT INTO jobs_new SELECT * FROM jobs')
    connection.exec_driver_sql('DROP TABLE jobs')
    connection.exec_driver_sql('ALTER TABLE jobs_new RENAME TO jobs')
    for statement in dependents:
        connection.exec_driver_sql(statement)
    connection.exec_driver_sql("CREATE UNIQUE INDEX ux_jobs_active_knowledge ON jobs(agency_id,scope) WHERE kind='knowledge_index' AND status IN ('queued','running')")
    connection.exec_driver_sql('''CREATE TABLE knowledge_documents (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
        current_version_id VARCHAR(36) REFERENCES knowledge_versions(id) ON DELETE RESTRICT,
        active BOOLEAN NOT NULL CHECK(active IN (0,1)), approved BOOLEAN NOT NULL CHECK(approved IN (0,1)),
        revision INTEGER NOT NULL CHECK(revision>=1), created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('CREATE INDEX ix_knowledge_documents_agency_id ON knowledge_documents(agency_id)')
    connection.exec_driver_sql('''CREATE TABLE knowledge_versions (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        document_id VARCHAR(36) NOT NULL REFERENCES knowledge_documents(id) ON DELETE RESTRICT,
        version INTEGER NOT NULL CHECK(version>=1), title VARCHAR(200) NOT NULL,
        document_type VARCHAR(30) NOT NULL CHECK(document_type IN ('service','case_study','experience','other')),
        text TEXT NOT NULL CHECK(length(trim(text))>0), demo BOOLEAN NOT NULL CHECK(demo IN (0,1)),
        content_hash VARCHAR(64) NOT NULL, created_at VARCHAR(32) NOT NULL,
        UNIQUE(document_id,version))''')
    connection.exec_driver_sql('''CREATE TABLE knowledge_chunks (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        version_id VARCHAR(36) NOT NULL REFERENCES knowledge_versions(id) ON DELETE RESTRICT,
        job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        embedding_id VARCHAR(36) NOT NULL REFERENCES embeddings(id) ON DELETE RESTRICT,
        ordinal INTEGER NOT NULL, start_offset INTEGER NOT NULL CHECK(start_offset>=0),
        end_offset INTEGER NOT NULL CHECK(end_offset>start_offset), token_count INTEGER NOT NULL CHECK(token_count BETWEEN 1 AND 180),
        text TEXT NOT NULL, settings JSON NOT NULL CHECK(json_valid(settings)),
        created_at VARCHAR(32) NOT NULL, UNIQUE(job_id,ordinal))''')
    connection.exec_driver_sql('CREATE INDEX ix_knowledge_chunks_version_id ON knowledge_chunks(version_id,job_id)')
    for table in ('knowledge_versions', 'knowledge_chunks'):
        connection.exec_driver_sql(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'Knowledge content is immutable'); END")
    connection.exec_driver_sql('''CREATE TRIGGER knowledge_version_owner BEFORE UPDATE OF current_version_id ON knowledge_documents
        WHEN NEW.current_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM knowledge_versions WHERE id=NEW.current_version_id AND document_id=NEW.id)
        BEGIN SELECT RAISE(ABORT,'Knowledge version belongs to another document'); END''')
