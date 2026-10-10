from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from app.modules.processing.job_model import Job, JobStage
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.processing.worker_main import Worker


def queue(client, lead, key='request-1', **body):
    return client.post(f"/api/v1/leads/{lead['id']}/analysis-jobs", headers={'Idempotency-Key': key}, json={'mode': 'live', **body})


def test_worker_availability_and_input_validation(client, job_lead, application, settings):
    assert queue(client, job_lead).json()['error']['code'] == 'WORKER_UNAVAILABLE'
    path = f"/api/v1/leads/{job_lead['id']}/analysis-jobs"
    assert client.post(path, json={'mode': 'live'}).status_code == 428
    assert queue(client, job_lead, key=' ').status_code == 422
    assert queue(client, job_lead, key='a' * 129).status_code == 422
    assert queue(client, job_lead, mode='cached').json()['error']['code'] == 'SAVED_EVIDENCE_REQUIRED'
    assert queue(client, job_lead, mode='uploaded', upload_token='not-real').json()['error']['code'] == 'UPLOAD_NOT_FOUND'
    assert queue(client, job_lead, mode='live', upload_token='unexpected').status_code == 422
    assert queue(client, job_lead, include_supporting_pages='true').status_code == 422


def test_same_key_replay_conflict_and_active_job(client, job_lead, registered_worker, application):
    first = queue(client, job_lead)
    assert first.status_code == 202
    assert first.headers['location'] == first.json()['poll_url']
    lead = client.get(f"/api/v1/leads/{job_lead['id']}").json()
    assert lead['processing_status'] == 'queued'
    assert lead['latest_job_id'] == first.json()['job_id']
    assert queue(client, job_lead).json() == first.json()
    assert queue(client, job_lead, include_supporting_pages=True).json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert queue(client, job_lead, key='other').json()['error']['code'] == 'ANALYSIS_ACTIVE'
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 1
        assert session.scalar(select(func.count()).select_from(JobStage)) == 9


def test_replay_precedes_archived_inputs_and_dead_worker(client, job_lead, application, settings):
    with Worker(application.state.database, settings):
        first = queue(client, job_lead).json()
    client.patch(f"/api/v1/campaigns/{job_lead['campaign_id']}", json={'archived': True}, headers={'If-Match': '"1"'})
    assert queue(client, job_lead).json() == first
    assert queue(client, job_lead, key='different').json()['error']['code'] == 'CAMPAIGN_ARCHIVED'


def test_concurrent_same_key_returns_one_run(settings, application, client, job_lead, registered_worker):
    settings.sqlite_busy_timeout_ms = 2000
    gate = Barrier(2)
    def post(_):
        gate.wait()
        return queue(client, job_lead)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(post, [1, 2]))
    assert [result.status_code for result in results] == [202, 202]
    assert results[0].json() == results[1].json()


def test_production_unavailable_site_fails_honestly_and_retry_snapshots_current_inputs(client, job_lead, registered_worker):
    first = queue(client, job_lead).json()
    registered_worker.run_once()
    polled = client.get(first['poll_url']).json()
    assert polled['status'] == 'failed'
    assert client.get(f"/api/v1/leads/{job_lead['id']}").json()['processing_status'] == 'failed'
    assert polled['errors'][0]['code'] == 'DNS_FAILURE'
    assert not any(stage['usable'] for stage in polled['stages'])
    client.patch(f"/api/v1/leads/{job_lead['id']}", json={'description': 'Changed company input'}, headers={'If-Match': '"1"'})
    retried = client.post(f"/api/v1/jobs/{first['job_id']}/retry", json={}, headers={'Idempotency-Key': 'retry-1'})
    assert retried.status_code == 202, retried.text
    second = retried.json()
    assert second['run_id'] != first['run_id']
    assert client.post(f"/api/v1/jobs/{first['job_id']}/retry", json={}, headers={'Idempotency-Key': 'retry-1'}).json() == second
    old_run = client.get('/api/v1/runs/' + first['run_id']).json()
    new_run = client.get('/api/v1/runs/' + second['run_id']).json()
    assert not old_run['is_current'] and 'LEAD_INPUT_CHANGED' in old_run['stale_reasons']
    assert old_run['input_snapshot']['lead']['description'] is None
    assert new_run['lead_input_revision'] == 2
    assert new_run['job']['retry_of_id'] == first['job_id']
    assert client.post(f"/api/v1/jobs/{first['job_id']}/retry", json={}, headers={'Idempotency-Key': 'request-1'}).status_code == 409


def test_cancel_queued_is_idempotent_and_deletion_cascades_jobs(client, job_lead, registered_worker, application):
    job = queue(client, job_lead).json()
    delete_path = f"/api/v1/leads/{job_lead['id']}?confirm=true"
    assert client.delete(delete_path, headers={'If-Match': '"1"'}).json()['error']['code'] == 'ANALYSIS_ACTIVE'
    cancelled = client.post(f"/api/v1/jobs/{job['job_id']}/cancel").json()
    assert cancelled['status'] == 'cancelled'
    assert client.post(f"/api/v1/jobs/{job['job_id']}/cancel").json() == cancelled
    assert client.delete(delete_path, headers={'If-Match': '"1"'}).status_code == 204
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(JobStage)) == 0
        assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 0


def test_history_pagination_missing_ids_and_immutable_inputs(client, job_lead, registered_worker, application):
    first = queue(client, job_lead).json()
    registered_worker.run_once()
    second = queue(client, job_lead, key='second').json()
    history = client.get(f"/api/v1/leads/{job_lead['id']}/runs?page_size=1").json()
    assert history['total'] == 2 and len(history['items']) == 1
    assert client.get(f'/api/v1/jobs/{uuid4()}').status_code == 404
    assert client.get(f'/api/v1/runs/{uuid4()}').status_code == 404
    assert client.get(f"/api/v1/leads/{job_lead['id']}/runs?page_size=101").status_code == 422
    for statement, target in [('UPDATE analysis_runs SET lead_input_revision=99 WHERE id=?', first['run_id']),
                              ('UPDATE jobs SET request_hash=? WHERE id=?', None)]:
        with pytest.raises(IntegrityError), application.state.database.engine.begin() as connection:
            arguments = (target,) if target else ('x' * 64, first['job_id'])
            connection.exec_driver_sql(statement, arguments)
