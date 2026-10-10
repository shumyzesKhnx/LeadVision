from concurrent.futures import ThreadPoolExecutor
import importlib
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, inspect
from sqlalchemy.exc import IntegrityError

from app.modules.foundation.hashing import content_hash
from app.modules.foundation.database_base import SchemaVersion
from app.modules.foundation.migration_runner import MIGRATIONS_DIR, SUPPORTED_SCHEMA_VERSION, migrate
from app.modules.foundation.database_session import Database
from app.main import create_app
from app.modules.leads.company_model import Company
from app.modules.leads.lead_model import Lead
from app.modules.leads.lead_fact_model import LeadFact
from app.modules.icp.icp_schema import CREATE_EXAMPLE


def setup_campaign(client, name='Campaign'):
    if client.get('/api/v1/agency').status_code == 404:
        client.post('/api/v1/agency', json={'name': 'Agency'})
    profile = client.post('/api/v1/icps', json=CREATE_EXAMPLE).json()
    result = client.post('/api/v1/campaigns', json={'name': name, 'icp_id': profile['id']})
    assert result.status_code == 201
    return result.json()


def add_lead(client, campaign, **changes):
    result = client.post('/api/v1/leads', json={'company_name': 'Example Company', 'website': 'https://example.com',
                                               'campaign_id': campaign['id'], **changes})
    assert result.status_code == 201, result.text
    return result.json()


def edit(client, lead, values, revision=1):
    return client.patch(f"/api/v1/leads/{lead['id']}", json=values, headers={'If-Match': f'"{revision}"'})


def test_create_defaults_provenance_and_real_campaign_count(client):
    campaign = setup_campaign(client)
    lead = add_lead(client, campaign, industry='SaaS', country='pk', employee_count=0)
    assert lead['pipeline_state'] == 'New'
    assert lead['employee_count'] == 0
    assert lead['contact_email'] is None
    assert lead['industry'] == 'software'
    assert lead['country'] == 'PK'
    assert lead['score'] is None
    assert lead['priority'] == 'Needs review'
    assert lead['evidence'] == [] and lead['drafts'] == []
    assert all(fact['source_category'] == 'user_provided' for fact in lead['provenance'])
    assert {fact['field_name'] for fact in lead['provenance']} == {'company_name', 'website', 'industry', 'country', 'employee_count'}
    assert lead['activities'][0]['action'] == 'lead.created'
    assert client.get(f"/api/v1/campaigns/{campaign['id']}").json()['lead_count'] == 1


def test_domain_duplicates_shared_identity_and_name_warnings(client, application):
    campaign = setup_campaign(client)
    first = add_lead(client, campaign)
    duplicate = client.post('/api/v1/leads', json={'company_name': 'Other', 'website': 'http://WWW.EXAMPLE.COM:80/x?tracking=1', 'campaign_id': campaign['id']})
    assert duplicate.status_code == 409
    assert duplicate.json()['error']['code'] == 'DUPLICATE_DOMAIN'
    assert duplicate.json()['error']['details'][0]['reason'] == first['id']
    second = add_lead(client, campaign, website='https://shop.example.com', company_name='  example company  ')
    assert second['warnings'] == ['POSSIBLE_NAME_DUPLICATE']
    another = add_lead(client, setup_campaign(client, 'Other'), industry='retail')
    assert first['company_id'] == another['company_id']
    assert another['industry'] == 'retail'
    assert client.get(f"/api/v1/leads/{first['id']}").json()['industry'] is None
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 2


@pytest.mark.parametrize('changes', [{'company_name': ''}, {'website': 'http://localhost'}, {'country': 'ZZ'},
    {'employee_count': -1}, {'employee_count': True}, {'employee_count': '20'}, {'contact_email': 'string'},
    {'company_name': None}, {'pipeline_state': 'Qualified'}, {'website': 'https://user:secret@example.com'}])
def test_invalid_lead_never_saves(client, changes):
    campaign = setup_campaign(client)
    result = client.post('/api/v1/leads', json={'company_name': 'Company', 'website': 'https://example.com', 'campaign_id': campaign['id'], **changes})
    assert result.status_code == 422
    assert client.get('/api/v1/leads').json()['total'] == 0


def test_corrections_append_facts_and_only_analytical_fields_change_input_revision(client):
    lead = add_lead(client, setup_campaign(client), industry='software')
    notes = edit(client, lead, {'notes': 'Call next week'}).json()
    assert notes['revision'] == 2 and notes['analytical_input_revision'] == 1
    changed = edit(client, lead, {'industry': 'retail', 'correction_reason': 'Corrected by operator'}, 2).json()
    assert changed['analytical_input_revision'] == 2
    assert changed['invalidation']['analytical_inputs_changed']
    assert changed['invalidation']['changed_fields'] == ['industry']
    clear = edit(client, lead, {'industry': None}, 3).json()
    assert clear['revision'] == 4 and clear['industry'] is None
    history = client.get(f"/api/v1/leads/{lead['id']}/facts").json()['items']
    facts = sorted([f for f in history if f['field_name'] == 'industry'], key=lambda fact: fact['revision'])
    assert [f['value'] for f in facts] == ['software', 'retail', None]
    assert facts[1]['supersedes_fact_id'] == facts[0]['id']
    assert facts[1]['correction_reason'] == 'Corrected by operator'
    assert edit(client, lead, {'industry': None}, 4).json()['revision'] == 4
    assert edit(client, lead, {'notes': 'Old editor'}, 1).status_code == 409
    assert client.patch(f"/api/v1/leads/{lead['id']}", json={'notes': 'Test'}).status_code == 428
    assert edit(client, lead, {'website': None}, 4).status_code == 422


def test_domain_correction_does_not_change_other_campaign_and_duplicate_correction_rolls_back(client):
    campaign = setup_campaign(client)
    lead = add_lead(client, campaign)
    shared = add_lead(client, setup_campaign(client, 'Other'))
    another = add_lead(client, campaign, website='https://other.example.com')
    assert edit(client, lead, {'website': another['website']}).status_code == 409
    assert client.get(f"/api/v1/leads/{lead['id']}").json()['revision'] == 1
    changed = edit(client, lead, {'website': 'https://new.example.com'}).json()
    assert changed['company_id'] != shared['company_id']
    assert client.get(f"/api/v1/leads/{shared['id']}").json()['normalized_domain'] == 'example.com'


def test_filters_unicode_search_and_pagination(client):
    campaign = setup_campaign(client)
    first = add_lead(client, campaign, company_name='شرکت Software')
    second = add_lead(client, campaign, website='https://two.example.com', company_name='Other')
    assert client.get('/api/v1/leads?q=Software').json()['items'][0]['id'] == first['id']
    assert client.get('/api/v1/leads?q=%25').json()['total'] == 0
    assert client.get('/api/v1/leads?priority=High').json()['total'] == 0
    assert client.get('/api/v1/leads?pipeline_state=Reviewed').json()['total'] == 0
    assert client.get('/api/v1/leads?priority=Needs%20review').json()['total'] == 2
    pages = [client.get(f'/api/v1/leads?sort=score&page_size=1&page={page}').json() for page in (1, 2)]
    assert {page['items'][0]['id'] for page in pages} == {first['id'], second['id']}
    assert client.get('/api/v1/leads?sort=unsafe').status_code == 422
    assert client.get('/api/v1/leads?page_size=101').status_code == 422


def test_delete_confirm_revision_cascade_and_shared_company(client, application):
    campaign = setup_campaign(client)
    lead = add_lead(client, campaign)
    shared = add_lead(client, setup_campaign(client, 'Other'))
    path = f"/api/v1/leads/{lead['id']}"
    assert client.delete(path, headers={'If-Match': '"1"'}).status_code == 409
    assert client.delete(path + '?confirm=true', headers={'If-Match': '"2"'}).status_code == 409
    deleted = client.delete(path + '?confirm=true', headers={'If-Match': '"1"'})
    assert deleted.status_code == 204 and deleted.content == b''
    assert client.get(path).status_code == 404
    assert client.get(f"/api/v1/leads/{shared['id']}").status_code == 200
    assert client.get(f"/api/v1/campaigns/{campaign['id']}").json()['lead_count'] == 0
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(LeadFact).where(LeadFact.lead_id == lead['id'])) == 0
        assert session.get(Company, shared['company_id']) is not None


def test_archive_blocks_creation_but_allows_history_read_and_correction(client):
    campaign = setup_campaign(client)
    lead = add_lead(client, campaign)
    client.patch(f"/api/v1/campaigns/{campaign['id']}", json={'archived': True}, headers={'If-Match': '"1"'})
    result = client.post('/api/v1/leads', json={'company_name': 'Other', 'website': 'https://other.example.com', 'campaign_id': campaign['id']})
    assert result.json()['error']['code'] == 'CAMPAIGN_ARCHIVED'
    assert client.get(f"/api/v1/leads/{lead['id']}").status_code == 200
    assert edit(client, lead, {'notes': 'Historical correction'}).status_code == 200


def test_activity_failure_rolls_back_lead_and_provenance(client, application, monkeypatch):
    campaign = setup_campaign(client)
    lead = add_lead(client, campaign)
    def fail(*args, **kwargs):
        raise RuntimeError('Injected activity failure')
    monkeypatch.setattr('app.modules.leads.leads_service.record_activity', fail)
    assert edit(client, lead, {'industry': 'software'}).status_code == 500
    assert client.get(f"/api/v1/leads/{lead['id']}").json() == lead
    assert client.post('/api/v1/leads', json={'company_name': 'Rollback', 'website': 'https://rollback.example.com', 'campaign_id': campaign['id']}).status_code == 500
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Lead)) == 1
        assert session.scalar(select(func.count()).select_from(Company)) == 1


def test_concurrent_creations_have_one_duplicate(settings, application):
    settings.sqlite_busy_timeout_ms = 2000
    with TestClient(application, base_url='http://127.0.0.1:8000') as client:
        campaign = setup_campaign(client)
        gate = Barrier(2)
        def create(name):
            gate.wait()
            return client.post('/api/v1/leads', json={'company_name': name, 'website': 'https://example.com', 'campaign_id': campaign['id']})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ['A', 'B']))
        assert sorted(result.status_code for result in results) == [201, 409]


def test_restart_preserves_lead_and_fact_history(settings):
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as client:
        lead = add_lead(client, setup_campaign(client))
        edit(client, lead, {'industry': 'software'})
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as client:
        assert client.get(f"/api/v1/leads/{lead['id']}").json()['revision'] == 2
        assert client.get(f"/api/v1/leads/{lead['id']}/facts").json()['total'] == 3


@pytest.mark.parametrize('orphan', [False, True])
def test_schema_four_upgrade_preserves_links_and_rolls_back_bad_legacy_lead(settings, orphan):
    settings.data_dir.mkdir()
    db = Database(settings)
    try:
        with db.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            for number, name in [(1, '001_foundation'), (2, '002_agency_services'), (3, '003_icps'), (4, '004_campaigns')]:
                importlib.import_module('app.modules.foundation.' + name).upgrade(connection)
                checksum = content_hash((MIGRATIONS_DIR / (name + '.py')).read_text(encoding='utf-8').encode())
                connection.execute(insert(SchemaVersion).values(version=number, checksum=checksum, applied_at='time'))
            connection.exec_driver_sql("INSERT INTO activities(id,lead_id,action,origin,created_at) VALUES('event',?,'legacy','api','time')", ('missing' if orphan else None,))
            connection.exec_driver_sql("INSERT INTO file_cleanup_tasks(id,artifact_key,reason,state,attempts,created_at,activity_id) VALUES('cleanup','evidence/x.txt','test','pending',0,'time','event')")
        if orphan:
            with pytest.raises((IntegrityError, RuntimeError), match="(?i)foreign key"):
                migrate(db.engine)
            assert 'leads' not in inspect(db.engine).get_table_names()
        else:
            assert migrate(db.engine) == SUPPORTED_SCHEMA_VERSION
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT activity_id FROM file_cleanup_tasks').scalar() == 'event'
            assert connection.exec_driver_sql('SELECT max(version) FROM schema_versions').scalar() == (4 if orphan else SUPPORTED_SCHEMA_VERSION)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
    finally:
        db.close()
