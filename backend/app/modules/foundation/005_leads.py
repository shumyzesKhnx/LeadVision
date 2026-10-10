"""Add company identities, campaign leads and append-only facts; preserve cleanup links."""

from sqlalchemy import Connection


def upgrade(connection: Connection) -> None:
    statements = [
        '''CREATE TABLE companies (
            id VARCHAR(36) NOT NULL PRIMARY KEY, normalized_domain VARCHAR(253) NOT NULL UNIQUE,
            created_at VARCHAR(32) NOT NULL
        )''',
        '''CREATE TABLE leads (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            campaign_id VARCHAR(36) NOT NULL REFERENCES campaigns(id) ON DELETE RESTRICT,
            company_id VARCHAR(36) NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
            company_name VARCHAR(200) NOT NULL CHECK(length(trim(company_name)) BETWEEN 1 AND 200),
            name_key VARCHAR(200) NOT NULL, website TEXT NOT NULL, normalized_url TEXT NOT NULL,
            industry VARCHAR(100), country VARCHAR(2), employee_count INTEGER CHECK(employee_count IS NULL OR employee_count >= 0),
            contact_name VARCHAR(200), contact_email VARCHAR(254), description TEXT, notes TEXT,
            pipeline_state VARCHAR(20) NOT NULL CHECK(pipeline_state IN ('New','Reviewed','Qualified','Contacted','Replied','Converted','Lost')),
            revision INTEGER NOT NULL CHECK(revision >= 1),
            analytical_input_revision INTEGER NOT NULL CHECK(analytical_input_revision >= 1),
            created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL,
            UNIQUE(campaign_id,company_id)
        )''',
        'CREATE INDEX ix_leads_campaign_id ON leads(campaign_id)',
        'CREATE INDEX ix_leads_company_id ON leads(company_id)',
        'CREATE INDEX ix_leads_company_name ON leads(company_name)',
        'CREATE INDEX ix_leads_name_key ON leads(name_key)',
        'CREATE INDEX ix_leads_campaign_state_time ON leads(campaign_id,pipeline_state,created_at,id)',
        '''CREATE TABLE lead_facts (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            lead_id VARCHAR(36) NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            field_name VARCHAR(100) NOT NULL, value JSON NOT NULL CHECK(json_valid(value)),
            source_category VARCHAR(30) NOT NULL CHECK(source_category IN ('user_provided','source_extracted','model_inferred')),
            verified BOOLEAN NOT NULL CHECK(verified IN (0,1)), actor_label VARCHAR(200),
            revision INTEGER NOT NULL CHECK(revision >= 1), supersedes_fact_id VARCHAR(36),
            correction_reason VARCHAR(500), recorded_at VARCHAR(32) NOT NULL,
            UNIQUE(lead_id,field_name,revision)
        )''',
        'CREATE INDEX ix_lead_facts_lead_id ON lead_facts(lead_id)',
        '''CREATE TRIGGER lead_facts_no_update BEFORE UPDATE ON lead_facts
           BEGIN SELECT RAISE(ABORT,'Lead facts are append-only'); END''',
        '''CREATE TABLE activities_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            agency_id VARCHAR(36) REFERENCES agencies(id) ON DELETE RESTRICT,
            campaign_id VARCHAR(36) REFERENCES campaigns(id) ON DELETE RESTRICT,
            lead_id VARCHAR(36) REFERENCES leads(id) ON DELETE CASCADE,
            action VARCHAR(100) NOT NULL, origin VARCHAR(20) NOT NULL,
            actor_label VARCHAR(200), old_value JSON, new_value JSON, event_key TEXT UNIQUE,
            created_at VARCHAR(32) NOT NULL,
            CONSTRAINT ck_activity_origin CHECK(origin IN ('operator','api','worker','import','n8n'))
        )''',
        'INSERT INTO activities_new SELECT * FROM activities',
        '''CREATE TABLE file_cleanup_tasks_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY, artifact_key TEXT NOT NULL,
            reason VARCHAR(200) NOT NULL, state VARCHAR(20) NOT NULL,
            attempts INTEGER NOT NULL CHECK(attempts >= 0), last_error VARCHAR(100),
            created_at VARCHAR(32) NOT NULL, completed_at VARCHAR(32),
            activity_id VARCHAR(36) REFERENCES activities_new(id) ON DELETE SET NULL,
            CONSTRAINT ck_cleanup_state CHECK(state IN ('pending','completed','failed'))
        )''',
        'INSERT INTO file_cleanup_tasks_new SELECT * FROM file_cleanup_tasks',
        'DROP TABLE file_cleanup_tasks',
        'DROP TABLE activities',
        'ALTER TABLE activities_new RENAME TO activities',
        'ALTER TABLE file_cleanup_tasks_new RENAME TO file_cleanup_tasks',
        'CREATE INDEX ix_activities_lead_id ON activities(lead_id)',
        'CREATE INDEX ix_activities_campaign_id ON activities(campaign_id)',
        'CREATE INDEX ix_file_cleanup_tasks_state ON file_cleanup_tasks(state)',
    ]
    for statement in statements:
        connection.exec_driver_sql(statement)
    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
        raise RuntimeError('Lead migration foreign key check failed.')
