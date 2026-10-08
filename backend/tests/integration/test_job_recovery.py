import importlib
import os
from pathlib import Path
import subprocess
import time

import pytest
from sqlalchemy import insert, inspect, select

from app.core.config import BACKEND_ROOT, PROJECT_ROOT
from app.core.hashing import content_hash
from app.db.base import SchemaVersion
from app.db.migration_runner import MIGRATIONS_DIR, SUPPORTED_SCHEMA_VERSION, migrate
from app.db.session import Database
from app.models.job import Job
from app.schemas.job import AnalysisJobCreate
from app.services import jobs
from app.services.workflow import StageResult, StageFailure, STAGES
from app.worker.main import Worker
from app.worker.queue import claim_next
from test_job_idempotency import queue


def success(context, snapshot, outputs):
    context.checkpoint()
    return StageResult(output={'test_only': True}, usable=True)


def test_changed_queued_inputs_fail_but_notes_do_not(client, job_lead, registered_worker):
    first = queue(client, job_lead).json()
    client.patch(f"/api/v1/leads/{job_lead['id']}", json={'notes': 'Non-analytical note'}, headers={'If-Match': '"1"'})
    assert claim_next(registered_worker.database, registered_worker.owner) == first['job_id']
    with registered_worker.database.transaction(immediate=True) as session:
        from app.worker.recovery import terminate
        terminate(session, session.get(Job, first['job_id']), 'cancelled')
    second = queue(client, job_lead, key='second').json()
    client.patch(f"/api/v1/leads/{job_lead['id']}", json={'description': 'Changed'}, headers={'If-Match': '"2"'})
    assert not registered_worker.run_once()
    result = client.get(second['poll_url']).json()
    assert result['status'] == 'failed' and result['errors'][0]['code'] == 'INPUT_CHANGED'


def test_fake_downstream_failure_is_partial_and_saved_stage_is_not_duplicated(client, job_lead, application, settings):
    def fail(*args):
        raise RuntimeError('C:/private/password secret diagnostic')
    handlers = {name: success for name in STAGES}
    handlers['business_analysis'] = fail
    with Worker(application.state.database, settings, handlers=handlers) as worker:
        job = queue(client, job_lead).json()
        worker.run_once()
        polled = client.get(job['poll_url']).json()
        assert polled['status'] == 'partial'
        assert polled['stages'][1]['output']['test_only']
        assert 'password' not in str(polled)
        # Completed stage replay cannot rewrite an output or duplicate its activity.
        # A terminal job rejects direct persistence as interrupted.
        with pytest.raises(StageFailure):
            worker._commit_stage(job['job_id'], 'acquire_text', StageResult(output={'changed': True}))


def test_one_automatic_retry_and_completed_with_explicit_fake_handlers(client, job_lead, application, settings):
    calls = 0
    def transient(context, snapshot, outputs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise StageFailure('RUNTIME_DISCONNECTED', retryable=True)
        return success(context, snapshot, outputs)
    handlers = {name: success for name in STAGES}
    handlers['business_analysis'] = transient
    with Worker(application.state.database, settings, handlers=handlers) as worker:
        job = queue(client, job_lead).json()
        worker.run_once()
        result = client.get(job['poll_url']).json()
        assert result['status'] == 'completed'
        assert calls == 2
        assert next(stage for stage in result['stages'] if stage['name'] == 'business_analysis')['attempts'] == 2
        assert result['progress'] == {'finished_stages': 9, 'total_stages': 9}


def test_retry_budget_is_bounded(client, job_lead, application, settings):
    calls = 0
    def fails(context, snapshot, outputs):
        nonlocal calls
        calls += 1
        raise StageFailure('RUNTIME_DISCONNECTED', retryable=True)
    with Worker(application.state.database, settings, handlers={'validate_inputs': fails}) as worker:
        job = queue(client, job_lead).json()
        worker.run_once()
        assert calls == 2
        assert client.get(job['poll_url']).json()['status'] == 'failed'


def test_cooperative_job_deadline(client, job_lead, application, settings):
    settings.job_deadline_seconds = 1
    def slow(context, snapshot, outputs):
        context.wait(2)
        return StageResult()
    with Worker(application.state.database, settings, handlers={'validate_inputs': slow}) as worker:
        job = queue(client, job_lead).json()
        worker.run_once()
        assert client.get(job['poll_url']).json()['errors'][0]['code'] == 'JOB_TIMEOUT'


def test_invalid_stage_output_is_safe(client, job_lead, application, settings):
    def invalid(*args):
        return {'output': {'diagnostic_path': 'C:/private/secret'}}
    with Worker(application.state.database, settings, handlers={'validate_inputs': invalid}) as worker:
        job = queue(client, job_lead).json()
        worker.run_once()
        result = client.get(job['poll_url'])
        assert result.json()['errors'][0]['code'] == 'INVALID_STAGE_OUTPUT'
        assert 'C:/private' not in result.text


def test_killed_worker_releases_os_lock_and_new_worker_recovers(client, job_lead, application, settings, monkeypatch):
    # Submission readiness is bypassed only in this test so the child can own the lock.
    monkeypatch.setattr(jobs, 'require_worker', lambda *args: None)
    queued = queue(client, job_lead).json()
    child_code = '''
from app.core.config import Settings
from app.db.session import Database
from app.worker.main import Worker
from app.worker.handlers import production_handlers
def slow(context, snapshot, outputs):
    while True:
        context.wait(0.1)
settings = Settings()
database = Database(settings)
handlers = production_handlers()
handlers['acquire_text'] = slow
with Worker(database, settings, handlers=handlers) as worker:
    worker.run_once()
'''
    child = subprocess.Popen([str(PROJECT_ROOT / '.venv/Scripts/python.exe'), '-c', child_code],
                             cwd=BACKEND_ROOT, env={**os.environ, 'LEADVISION_DATA_DIR': str(settings.data_dir),
                                                   'LEADVISION_OLLAMA_BASE_URL': 'http://127.0.0.1:1'},
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        until = time.monotonic() + 10
        while time.monotonic() < until:
            with application.state.database.sessions() as session:
                job = session.get(Job, queued['job_id'])
                if job.status == 'running' and job.current_stage == 'acquire_text':
                    break
            if child.poll() is not None:
                raise AssertionError('Child worker exited before processing began.')
            time.sleep(0.05)
        else:
            raise AssertionError('Child worker did not claim its job.')
        child.kill()
        child.communicate(timeout=5)
        with Worker(application.state.database, settings):
            recovered = client.get(queued['poll_url']).json()
            assert recovered['status'] == 'failed'
            assert recovered['errors'][0]['code'] == 'JOB_INTERRUPTED'
            retry = client.post(f"/api/v1/jobs/{queued['job_id']}/retry", json={}, headers={'Idempotency-Key': 'after-crash'}).json()
            assert retry['run_id'] != queued['run_id']
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=5)
        if child.stdout:
            child.stdout.close()
        if child.stderr:
            child.stderr.close()


@pytest.mark.parametrize('broken', [False, True])
def test_schema_five_upgrade_is_atomic(settings, monkeypatch, broken):
    settings.data_dir.mkdir()
    database = Database(settings)
    try:
        with database.engine.begin() as connection:
            SchemaVersion.__table__.create(connection)
            for source in sorted(MIGRATIONS_DIR.glob('00[1-5]_*.py')):
                importlib.import_module('app.db.migrations.' + source.stem).upgrade(connection)
                connection.execute(insert(SchemaVersion).values(version=int(source.name[:3]),
                    checksum=content_hash(source.read_text(encoding='utf-8').encode()), applied_at='time'))
            connection.exec_driver_sql("INSERT INTO activities(id,action,origin,created_at) VALUES('preserved','legacy','api','time')")
        if broken:
            module = importlib.import_module('app.db.migrations.006_jobs_runs')
            original = module.upgrade
            def fail(connection):
                original(connection)
                raise RuntimeError('Injected DDL failure')
            monkeypatch.setattr(module, 'upgrade', fail)
            with pytest.raises(RuntimeError):
                migrate(database.engine)
            assert 'jobs' not in inspect(database.engine).get_table_names()
        else:
            assert migrate(database.engine) == SUPPORTED_SCHEMA_VERSION
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql('SELECT id FROM activities').scalar() == 'preserved'
            assert connection.exec_driver_sql('SELECT max(version) FROM schema_versions').scalar() == (5 if broken else SUPPORTED_SCHEMA_VERSION)
            assert not connection.exec_driver_sql('PRAGMA foreign_key_check').all()
    finally:
        database.close()
