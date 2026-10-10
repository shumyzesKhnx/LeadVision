from concurrent.futures import ThreadPoolExecutor
import importlib
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, inspect
from sqlalchemy.exc import IntegrityError

from app.modules.foundation.hashing import content_hash
from app.modules.foundation.errors import AppError
from app.modules.foundation.database_base import SchemaVersion
from app.modules.foundation.migration_runner import MIGRATIONS_DIR, SUPPORTED_SCHEMA_VERSION, migrate
from app.modules.foundation.database_session import Database
from app.main import create_app
from app.modules.icp.icp_model import ICP, ICPVersion
from app.modules.processing.activity_model import Activity
from app.modules.icp.icp_schema import CREATE_EXAMPLE
from app.modules.processing.freshness_service import configuration_is_current
from app.modules.icp.icp_service import require_icp


def create_profile(client, **changes):
    if client.get('/api/v1/agency').status_code == 404:
        assert client.post('/api/v1/agency', json={'name': 'TechNova'}).status_code == 201
    response = client.post('/api/v1/icps', json={**CREATE_EXAMPLE, **changes})
    assert response.status_code == 201, response.text
    return response


def patch(client, profile, body, revision=1):
    return client.patch(f"/api/v1/icps/{profile['id']}", json=body, headers={'If-Match': f'"{revision}"'})


def test_create_read_options_and_history(client):
    assert client.post('/api/v1/icps', json=CREATE_EXAMPLE).status_code == 404
    response = create_profile(client)
    profile = response.json()
    assert response.headers['etag'] == '"1"'
    assert profile['current_version']['version'] == 1
    assert profile['eligible_components'] == ['industry', 'geography', 'size', 'semantic']
    assert profile['resolved_countries'] == ['GB']
    assert client.get(f"/api/v1/icps/{profile['id']}").json() == profile
    assert client.get('/api/v1/icps').json()['total'] == 1
    assert client.get(f"/api/v1/icps/{profile['id']}/versions").json()['items'] == [profile['current_version']]
    options = client.get('/api/v1/icps/options').json()
    assert len(options['country_codes']) == 249
    assert options['regions']['uk'] == ['GB']
    assert client.delete(f"/api/v1/icps/{profile['id']}").status_code == 405


def test_edit_versions_semantic_reuse_and_name_only_changes(client, application):
    first = create_profile(client).json()
    renamed = patch(client, first, {'name': 'UK SaaS'}).json()
    assert renamed['revision'] == 2
    assert renamed['current_version'] == first['current_version']
    assert not renamed['invalidation']['scores_changed']
    weights = {**first['current_version']['config']['weights'], 'industry': 30}
    weighted = patch(client, first, {'weights': weights}, 2).json()
    assert weighted['current_version']['version'] == 2
    assert weighted['invalidation']['scores_changed']
    assert not weighted['invalidation']['semantic_changed']
    edited = patch(client, first, {'target_text': 'UK software companies wanting SEO.'}, 3).json()
    assert edited['current_version']['version'] == 3
    assert edited['invalidation']['semantic_changed']
    history = client.get(f"/api/v1/icps/{first['id']}/versions").json()
    assert [v['version'] for v in history['items']] == [3, 2, 1]
    assert history['items'][-1] == first['current_version']
    with application.state.database.sessions() as session:
        current = require_icp(session, first['id'])
        assert not configuration_is_current(current, first['current_version']['id'])
        assert configuration_is_current(current, edited['current_version']['id'])


def test_noop_and_canonicalization_do_not_append_versions(client, application):
    first = create_profile(client).json()
    current = patch(client, first, {'criteria': {'industries': ['SaaS', 'software'], 'countries': ['UK'],
                                               'employee_min': 20, 'employee_max': 100}}).json()
    assert current['revision'] == 1
    assert current['current_version'] == first['current_version']
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ICPVersion)) == 1
        assert session.scalar(select(func.count()).select_from(Activity)) == 2


@pytest.mark.parametrize('body,code', [
    ({'criteria': {'employee_min': 100, 'employee_max': 20}}, 'INVALID_SIZE_RANGE'),
    ({'criteria': {'employee_min': -1}}, 'VALIDATION_ERROR'),
    ({'criteria': {'regions': ['unknown']}}, 'UNKNOWN_REGION'),
    ({'weights': {'semantic': -1}}, 'INVALID_WEIGHTS'),
    ({'weights': {'industry': 0, 'geography': 0, 'size': 0, 'semantic': 0}}, 'INVALID_WEIGHTS'),
    ({'thresholds': {'medium': 75, 'high': 75}}, 'INVALID_THRESHOLDS'),
    ({'thresholds': {'minimum_coverage': 2}}, 'INVALID_THRESHOLDS'),
    ({'name': ' '}, 'VALIDATION_ERROR'),
    ({'target_text': ''}, 'INVALID_WEIGHTS'),
    ({'desired_needs': [' ']}, 'VALIDATION_ERROR'),
    ({'agency_id': str(uuid4())}, 'VALIDATION_ERROR'),
])
def test_invalid_create_never_saves_partial_profile(client, body, code):
    client.post('/api/v1/agency', json={'name': 'Agency'})
    response = client.post('/api/v1/icps', json={**CREATE_EXAMPLE, **body})
    assert response.status_code == 422, response.text
    assert response.json()['error']['code'] == code
    assert client.get('/api/v1/icps').json()['total'] == 0


def test_visual_calibration_cannot_be_bypassed(client):
    client.post('/api/v1/agency', json={'name': 'Agency'})
    for change in [{'weights': {'visual': 5}}, {'weights': {'visual': 5}, 'visual_calibration_id': 'invented'}]:
        response = client.post('/api/v1/icps', json={**CREATE_EXAMPLE, **change})
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'VISUAL_CALIBRATION_REQUIRED'


def test_archive_reactivate_and_pagination(client, application):
    first = create_profile(client).json()
    second = create_profile(client, name='Another profile').json()
    archived = patch(client, first, {'archived': True}).json()
    assert archived['current_version'] == first['current_version']
    assert client.get('/api/v1/icps').json()['total'] == 1
    assert client.get('/api/v1/icps?include_archived=true').json()['total'] == 2
    assert client.get(f"/api/v1/icps/{first['id']}/versions").json()['total'] == 1
    with application.state.database.sessions() as session:
        with pytest.raises(AppError, match='ICP_ARCHIVED'):
            require_icp(session, first['id'], selectable=True)
    assert patch(client, first, {'archived': False}, 2).status_code == 200
    pages = [client.get(f'/api/v1/icps?page={page}&page_size=1').json() for page in (1, 2)]
    assert {page['items'][0]['id'] for page in pages} == {first['id'], second['id']}
    assert client.get('/api/v1/icps?page_size=101').status_code == 422
    assert client.get(f'/api/v1/icps/{uuid4()}').status_code == 404
    assert client.get('/api/v1/icps/not-a-uuid').status_code == 422


def test_edit_headers_and_invalid_patch(client):
    first = create_profile(client).json()
    path = f"/api/v1/icps/{first['id']}"
    assert client.patch(path, json={'name': 'Edit'}).status_code == 428
    assert client.patch(path, headers={'If-Match': '1'}, json={'name': 'Edit'}).status_code == 422
    assert patch(client, first, {'name': 'Edit'}, 2).status_code == 409
    for body in [{}, {'name': None}, {'criteria': None}, {'archived': 'true'},
                 {'desired_needs': ['']}, {'extra': 'field'}]:
        assert patch(client, first, body).status_code == 422
    assert client.get(path).json() == first


def test_activity_failure_rolls_back_pointer_and_version(client, application, monkeypatch):
    first = create_profile(client).json()
    def fail(*args, **kwargs):
        raise RuntimeError('Simulated activity failure')
    monkeypatch.setattr('app.modules.icp.icp_service.record_activity', fail)
    assert patch(client, first, {'target_text': 'New desired customers'}).status_code == 500
    assert client.get(f"/api/v1/icps/{first['id']}").json() == first
    assert client.post('/api/v1/icps', json=CREATE_EXAMPLE).status_code == 500
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ICP)) == 1
        assert session.scalar(select(func.count()).select_from(ICPVersion)) == 1


def test_database_history_is_immutable_and_pointer_belongs_to_profile(client, application):
    first = create_profile(client).json()
    second = create_profile(client, name='Second').json()
    db = application.state.database
    statements = [
        ('UPDATE icp_versions SET version=99 WHERE id=?', (first['current_version']['id'],)),
        ('DELETE FROM icp_versions WHERE id=?', (first['current_version']['id'],)),
        ('UPDATE icps SET current_version_id=? WHERE id=?', (second['current_version']['id'], first['id'])),
    ]
    for statement, arguments in statements:
        with pytest.raises(IntegrityError), db.engine.begin() as connection:
            connection.exec_driver_sql(statement, arguments)


def test_competing_config_edits_preserve_one_winner(settings, application):
    settings.sqlite_busy_timeout_ms = 2000
    with TestClient(application, base_url='http://127.0.0.1:8000') as client:
        first = create_profile(client).json()
        gate = Barrier(2)
        def edit(text):
            gate.wait()
            return patch(client, first, {'target_text': text})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(edit, ['Customers A', 'Customers B']))
        assert sorted(r.status_code for r in responses) == [200, 409]
        assert client.get(f"/api/v1/icps/{first['id']}/versions").json()['total'] == 2


def test_profile_history_survives_restart(settings):
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as first:
        original = create_profile(first).json()
        assert patch(first, original, {'preferences_text': 'Prefer established companies.'}).status_code == 200
    with TestClient(create_app(settings), base_url='http://127.0.0.1:8000') as second:
        saved = second.get(f"/api/v1/icps/{original['id']}").json()
        assert saved['revision'] == 2
        assert saved['current_version']['version'] == 2
        assert second.get(f"/api/v1/icps/{original['id']}/versions").json()['total'] == 2


@pytest.mark.parametrize('broken', [False, True])
def test_schema_two_upgrade_preserves_workspace_and_rolls_back_failure(settings, monkeypatch, broken):
    settings.data_dir.mkdir()
    db = Database(settings)
    try:
        with db.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            for number, name in [(1, '001_foundation'), (2, '002_agency_services')]:
                importlib.import_module('app.modules.foundation.' + name).upgrade(connection)
                checksum = content_hash((MIGRATIONS_DIR / (name + '.py')).read_text(encoding='utf-8').encode())
                connection.execute(insert(SchemaVersion).values(version=number, checksum=checksum, applied_at='2026-10-08T00:00:00Z'))
            connection.exec_driver_sql("INSERT INTO agencies VALUES ('agency',1,'Existing','Profile',NULL,2,'time','time')")
            connection.exec_driver_sql("INSERT INTO services VALUES ('service','agency','SEO','Offer',1,3,'time','time')")
        if broken:
            module = importlib.import_module('app.modules.foundation.003_icps')
            original = module.upgrade
            def fail(connection):
                original(connection)
                raise RuntimeError('Injected migration failure')
            monkeypatch.setattr(module, 'upgrade', fail)
            with pytest.raises(RuntimeError):
                migrate(db.engine)
            assert 'icps' not in inspect(db.engine).get_table_names()
        else:
            assert migrate(db.engine) == SUPPORTED_SCHEMA_VERSION
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT name,revision FROM agencies').one() == ('Existing', 2)
            assert connection.exec_driver_sql('SELECT name,revision FROM services').one() == ('SEO', 3)
            assert connection.exec_driver_sql('SELECT max(version) FROM schema_versions').scalar() == (2 if broken else SUPPORTED_SCHEMA_VERSION)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
    finally:
        db.close()
