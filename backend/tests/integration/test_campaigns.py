"""Campaign lifecycle, linked targeting and atomic upgrade checks."""

from concurrent.futures import ThreadPoolExecutor
import importlib
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, insert, select
from sqlalchemy.exc import IntegrityError

from app.modules.foundation.errors import AppError
from app.modules.foundation.hashing import content_hash
from app.modules.foundation.database_base import SchemaVersion
from app.modules.foundation.migration_runner import MIGRATIONS_DIR, SUPPORTED_SCHEMA_VERSION, migrate
from app.modules.foundation.database_session import Database
from app.main import create_app
from app.modules.campaigns.campaign_model import Campaign
from app.modules.processing.activity_model import Activity
from app.modules.icp.icp_schema import CREATE_EXAMPLE
from app.modules.campaigns.campaign_service import require_campaign
from app.modules.icp.icp_service import require_icp
from app.modules.processing.freshness_service import campaign_configuration_is_current


def setup_icp(client):
    if client.get('/api/v1/agency').status_code == 404:
        assert client.post('/api/v1/agency', json={'name': 'TechNova'}).status_code == 201
    result = client.post('/api/v1/icps', json=CREATE_EXAMPLE)
    assert result.status_code == 201
    return result.json()


def create_campaign(client, profile, name='Website prospects'):
    result = client.post('/api/v1/campaigns', json={'name': name, 'icp_id': profile['id']})
    assert result.status_code == 201, result.text
    return result.json()


def patch(client, campaign, body, revision=1):
    return client.patch(f"/api/v1/campaigns/{campaign['id']}", json=body, headers={'If-Match': f'"{revision}"'})


def test_create_read_two_independent_campaigns_and_pagination(client):
    assert client.get('/api/v1/campaigns').status_code == 404
    profile = setup_icp(client)
    first = create_campaign(client, profile)
    other_profile = setup_icp(client)
    second = create_campaign(client, other_profile, name='Other prospects')
    assert first['analysis_allowed'] is True
    assert first['lead_count'] == 0
    assert first['current_icp_version_id'] == profile['current_version']['id']
    assert client.get(f"/api/v1/campaigns/{first['id']}").json() == first
    pages = [client.get(f'/api/v1/campaigns?page={page}&page_size=1').json() for page in (1, 2)]
    assert {page['items'][0]['id'] for page in pages} == {first['id'], second['id']}
    assert first['icp_id'] != second['icp_id']
    assert client.get('/api/v1/campaigns?page_size=101').status_code == 422
    assert client.get(f'/api/v1/campaigns/{uuid4()}').status_code == 404
    assert client.get('/api/v1/campaigns/not-a-uuid').status_code == 422
    assert client.delete(f"/api/v1/campaigns/{first['id']}").status_code == 405


@pytest.mark.parametrize('change', [{'name': ''}, {'name': ' '}, {'name': 'x' * 201},
    {'icp_id': 'not-a-uuid'}, {'name': None}, {'description': 'x' * 5001}, {'unknown': True}])
def test_invalid_campaign_does_not_save(client, change):
    profile = setup_icp(client)
    result = client.post('/api/v1/campaigns', json={'name': 'Campaign', 'icp_id': profile['id'], **change})
    assert result.status_code == 422
    assert client.get('/api/v1/campaigns').json()['total'] == 0


def test_missing_and_archived_icp_are_rejected(client):
    profile = setup_icp(client)
    assert client.post('/api/v1/campaigns', json={'name': 'Campaign', 'icp_id': str(uuid4())}).status_code == 404
    client.patch(f"/api/v1/icps/{profile['id']}", json={'archived': True}, headers={'If-Match': '"1"'})
    result = client.post('/api/v1/campaigns', json={'name': 'Campaign', 'icp_id': profile['id']})
    assert result.status_code == 409
    assert result.json()['error']['code'] == 'ICP_UNAVAILABLE'


def test_edits_noop_headers_and_description_clear(client, application):
    campaign = create_campaign(client, setup_icp(client))
    path = f"/api/v1/campaigns/{campaign['id']}"
    assert client.patch(path, json={'name': 'Rename'}).status_code == 428
    assert client.patch(path, json={'name': 'Rename'}, headers={'If-Match': '1'}).status_code == 422
    result = patch(client, campaign, {'name': '  Updated  ', 'description': 'Notes'})
    assert result.status_code == 200
    assert result.headers['etag'] == '"2"'
    assert result.json()['name'] == 'Updated'
    assert not result.json()['invalidation']['targeting_changed']
    assert patch(client, campaign, {'name': 'Stale'}).status_code == 409
    assert patch(client, campaign, {'description': None}, 2).json()['revision'] == 3
    assert patch(client, campaign, {'name': 'Updated'}, 3).json()['revision'] == 3
    for body in [{}, {'name': None}, {'icp_id': None}, {'archived': None}, {'archived': 'false'}]:
        assert patch(client, campaign, body, 3).status_code == 422
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Activity).where(Activity.campaign_id == campaign['id'])) == 3


def test_archive_preserves_history_and_preflight_checks(client, application):
    profile = setup_icp(client)
    campaign = create_campaign(client, profile)
    archived = patch(client, campaign, {'archived': True}).json()
    assert not archived['analysis_allowed']
    assert archived['analysis_blocked_reason'] == 'CAMPAIGN_ARCHIVED'
    assert client.get('/api/v1/campaigns').json()['total'] == 0
    assert client.get('/api/v1/campaigns?include_archived=true').json()['total'] == 1
    assert client.get(f"/api/v1/campaigns/{campaign['id']}").status_code == 200
    with application.state.database.sessions() as session:
        with pytest.raises(AppError, match='CAMPAIGN_ARCHIVED'):
            require_campaign(session, campaign['id'], for_work=True)
        assert session.scalar(select(func.count()).select_from(Activity).where(Activity.campaign_id == campaign['id'])) == 2
    client.patch(f"/api/v1/icps/{profile['id']}", json={'archived': True}, headers={'If-Match': '"1"'})
    assert patch(client, campaign, {'archived': False}, 2).json()['error']['code'] == 'ICP_UNAVAILABLE'
    client.patch(f"/api/v1/icps/{profile['id']}", json={'archived': False}, headers={'If-Match': '"2"'})
    assert patch(client, campaign, {'archived': False}, 2).json()['analysis_allowed']
    with application.state.database.sessions() as session:
        assert require_campaign(session, campaign['id'], for_work=True).revision == 3


def test_icp_changes_update_current_targeting_without_rewriting_old_versions(client, application):
    profile = setup_icp(client)
    campaign = create_campaign(client, profile)
    create_campaign(client, profile, name='Second campaign')
    result = client.patch(f"/api/v1/icps/{profile['id']}", json={'target_text': 'Updated target companies'},
                          headers={'If-Match': '"1"'}).json()
    assert result['invalidation']['affected_campaigns'] == 2
    assert result['invalidation']['affected_results'] == 0
    current = client.get(f"/api/v1/campaigns/{campaign['id']}").json()
    assert current['revision'] == 1
    assert current['current_icp_version'] == 2
    with application.state.database.sessions() as session:
        stored_campaign = require_campaign(session, campaign['id'])
        stored_profile = require_icp(session, profile['id'])
        assert not campaign_configuration_is_current(stored_campaign, stored_profile, profile['id'], profile['current_version']['id'])
        assert campaign_configuration_is_current(stored_campaign, stored_profile, profile['id'], current['current_icp_version_id'])
    other = setup_icp(client)
    swapped = patch(client, campaign, {'icp_id': other['id']}).json()
    assert swapped['invalidation']['targeting_changed']
    assert swapped['current_icp_version_id'] == other['current_version']['id']
    history = client.get(f"/api/v1/icps/{profile['id']}/versions").json()['items']
    assert history[-1] == profile['current_version']
    with application.state.database.sessions() as session:
        assert not campaign_configuration_is_current(require_campaign(session, campaign['id']),
            require_icp(session, other['id']), profile['id'], current['current_icp_version_id'])


def test_archiving_icp_blocks_existing_campaign_but_reads_remain(client, application):
    profile = setup_icp(client)
    campaign = create_campaign(client, profile)
    result = client.patch(f"/api/v1/icps/{profile['id']}", json={'archived': True}, headers={'If-Match': '"1"'}).json()
    assert result['invalidation']['affected_campaigns'] == 1
    read = client.get(f"/api/v1/campaigns/{campaign['id']}").json()
    assert read['analysis_blocked_reason'] == 'ICP_UNAVAILABLE'
    with application.state.database.sessions() as session:
        with pytest.raises(AppError, match='ICP_UNAVAILABLE'):
            require_campaign(session, campaign['id'], for_work=True)


def test_failed_activity_rolls_back_create_and_edit(client, application, monkeypatch):
    profile = setup_icp(client)
    campaign = create_campaign(client, profile)
    def fail(*args, **kwargs):
        raise RuntimeError('Injected activity failure')
    monkeypatch.setattr('app.modules.campaigns.campaign_service.record_activity', fail)
    assert patch(client, campaign, {'archived': True}).status_code == 500
    assert client.get(f"/api/v1/campaigns/{campaign['id']}").json() == campaign
    assert client.post('/api/v1/campaigns', json={'name': 'Rollback', 'icp_id': profile['id']}).status_code == 500
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Campaign)) == 1


def test_competing_campaign_edits_have_one_winner(settings, application):
    settings.sqlite_busy_timeout_ms = 2000
    with TestClient(application, base_url='http://127.0.0.1:8000') as client:
        campaign = create_campaign(client, setup_icp(client))
        gate = Barrier(2)
        def edit(name):
            gate.wait()
            return patch(client, campaign, {'name': name})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ['A', 'B']))
        assert sorted(r.status_code for r in results) == [200, 409]


def test_campaign_survives_restart(settings):
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as client:
        campaign = create_campaign(client, setup_icp(client))
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as client:
        assert client.get(f"/api/v1/campaigns/{campaign['id']}").json() == campaign


def test_campaign_and_activity_foreign_keys(client, application):
    campaign = create_campaign(client, setup_icp(client))
    with pytest.raises(IntegrityError), application.state.database.engine.begin() as connection:
        connection.exec_driver_sql('UPDATE campaigns SET agency_id=? WHERE id=?', ('missing', campaign['id']))
    with pytest.raises(IntegrityError), application.state.database.engine.begin() as connection:
        connection.exec_driver_sql('UPDATE campaigns SET icp_id=? WHERE id=?', ('missing', campaign['id']))
    with pytest.raises(IntegrityError), application.state.database.engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO activities(id,campaign_id,action,origin,created_at) VALUES ('bad','missing','test','api','time')")
    with pytest.raises(IntegrityError), application.state.database.engine.begin() as connection:
        connection.exec_driver_sql('DELETE FROM icps WHERE id=?', (campaign['icp_id'],))


@pytest.mark.parametrize('orphan', [False, True])
def test_upgrade_keeps_activity_cleanup_links_and_rolls_back_orphan(settings, orphan):
    settings.data_dir.mkdir()
    db = Database(settings)
    try:
        with db.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            for number, name in [(1, '001_foundation'), (2, '002_agency_services'), (3, '003_icps')]:
                importlib.import_module('app.modules.foundation.' + name).upgrade(connection)
                checksum = content_hash((MIGRATIONS_DIR / (name + '.py')).read_text(encoding='utf-8').encode())
                connection.execute(insert(SchemaVersion).values(version=number, checksum=checksum, applied_at='time'))
            connection.exec_driver_sql("INSERT INTO activities (id,campaign_id,action,origin,created_at) VALUES ('event',?,'legacy','api','time')", ('missing' if orphan else None,))
            connection.exec_driver_sql("INSERT INTO file_cleanup_tasks(id,artifact_key,reason,state,attempts,created_at,activity_id) VALUES('cleanup','evidence/x.txt','test','pending',0,'time','event')")
        if orphan:
            with pytest.raises((IntegrityError, RuntimeError), match="(?i)foreign key"):
                migrate(db.engine)
            assert 'campaigns' not in inspect(db.engine).get_table_names()
        else:
            assert migrate(db.engine) == SUPPORTED_SCHEMA_VERSION
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT activity_id FROM file_cleanup_tasks').scalar() == 'event'
            assert connection.exec_driver_sql('SELECT max(version) FROM schema_versions').scalar() == (3 if orphan else SUPPORTED_SCHEMA_VERSION)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
    finally:
        db.close()
