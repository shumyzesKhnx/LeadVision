"""Outreach queue, source snapshots and immutable text/review history."""


def upgrade(connection):
    ddl = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name='jobs'").scalar_one()
    old = "CHECK(kind IN ('analysis','knowledge_index')) CHECK((kind='analysis' AND lead_id IS NOT NULL) OR (kind='knowledge_index' AND lead_id IS NULL))"
    if old not in ddl:
        raise RuntimeError('Unexpected queue schema; migration refused.')
    dependents = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE tbl_name='jobs' AND type IN ('index','trigger') AND sql IS NOT NULL").scalars().all()
    ddl = ddl.replace('CREATE TABLE "jobs"', 'CREATE TABLE jobs_new', 1) if 'CREATE TABLE "jobs"' in ddl else ddl.replace('CREATE TABLE jobs', 'CREATE TABLE jobs_new', 1)
    ddl = ddl.replace(old, "CHECK(kind IN ('analysis','knowledge_index','outreach')) CHECK((kind IN ('analysis','outreach') AND lead_id IS NOT NULL) OR (kind='knowledge_index' AND lead_id IS NULL))")
    connection.exec_driver_sql(ddl)
    connection.exec_driver_sql('INSERT INTO jobs_new SELECT * FROM jobs')
    connection.exec_driver_sql('DROP TABLE jobs')
    connection.exec_driver_sql('ALTER TABLE jobs_new RENAME TO jobs')
    for statement in dependents:
        connection.exec_driver_sql(statement)
    connection.exec_driver_sql("CREATE UNIQUE INDEX ux_jobs_active_outreach ON jobs(lead_id) WHERE kind='outreach' AND status IN ('queued','running')")
    connection.exec_driver_sql('''CREATE TABLE outreach_drafts (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        agency_id VARCHAR(36) NOT NULL REFERENCES agencies(id) ON DELETE RESTRICT,
        lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        job_id VARCHAR(36) NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
        service_id VARCHAR(36) NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL CHECK(revision>=1), grounding JSON NOT NULL CHECK(json_valid(grounding)),
        retrieval JSON NOT NULL CHECK(json_valid(retrieval)), provenance JSON NOT NULL CHECK(json_valid(provenance)),
        warnings JSON NOT NULL CHECK(json_valid(warnings)), created_at VARCHAR(32) NOT NULL)''')
    connection.exec_driver_sql('CREATE INDEX ix_outreach_drafts_lead_id ON outreach_drafts(lead_id)')
    connection.exec_driver_sql('''CREATE TABLE outreach_revisions (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        draft_id VARCHAR(36) NOT NULL REFERENCES outreach_drafts(id) ON DELETE CASCADE,
        number INTEGER NOT NULL CHECK(number>=1),
        state VARCHAR(20) NOT NULL CHECK(state IN ('Generated','Edited','Approved','Rejected')),
        subject VARCHAR(200) NOT NULL CHECK(length(subject) BETWEEN 3 AND 200),
        body TEXT NOT NULL CHECK(length(body) BETWEEN 20 AND 2000),
        claims JSON NOT NULL CHECK(json_valid(claims)),
        unresolved_claims JSON NOT NULL CHECK(json_valid(unresolved_claims)),
        reviewer VARCHAR(100), reason VARCHAR(500), created_at VARCHAR(32) NOT NULL,
        CHECK(state NOT IN ('Approved','Rejected') OR (reviewer IS NOT NULL AND length(trim(reviewer))>0)),
        CHECK(state!='Rejected' OR (reason IS NOT NULL AND length(trim(reason))>0)), UNIQUE(draft_id,number))''')
    connection.exec_driver_sql('''CREATE TABLE draft_sources (
        id VARCHAR(36) PRIMARY KEY NOT NULL,
        draft_id VARCHAR(36) NOT NULL REFERENCES outreach_drafts(id) ON DELETE CASCADE,
        source_id VARCHAR(100) NOT NULL, snapshot JSON NOT NULL CHECK(json_valid(snapshot)),
        UNIQUE(draft_id,source_id))''')
    connection.exec_driver_sql('''CREATE TRIGGER outreach_owner BEFORE INSERT ON outreach_drafts
        WHEN NOT EXISTS (SELECT 1 FROM leads l JOIN campaigns c ON c.id=l.campaign_id
             JOIN services s ON s.id=NEW.service_id JOIN jobs j ON j.id=NEW.job_id
             WHERE l.id=NEW.lead_id AND c.agency_id=NEW.agency_id AND s.agency_id=NEW.agency_id
             AND j.agency_id=NEW.agency_id AND j.lead_id=NEW.lead_id AND j.kind='outreach')
        BEGIN SELECT RAISE(ABORT,'Outreach sources belong to another workspace'); END''')
    for table in ('outreach_revisions', 'draft_sources'):
        connection.exec_driver_sql(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'Outreach history is immutable'); END")
    connection.exec_driver_sql("CREATE TRIGGER outreach_grounding_no_update BEFORE UPDATE OF grounding,retrieval,provenance,warnings ON outreach_drafts BEGIN SELECT RAISE(ABORT,'Outreach grounding is immutable'); END")
