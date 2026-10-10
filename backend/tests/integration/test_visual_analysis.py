import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.modules.computer_vision.visual_analysis_model import VisualAnalysis
from app.modules.evidence.evidence_model import Evidence
from test_saved_evidence import upload, submit, screenshot


def test_visual_worker_result_cache_history_and_immutable_original(client, job_lead, registered_worker, application):
    original = screenshot()
    receipt = upload(client, job_lead, image=original).json()
    job = submit(client, job_lead, receipt).json()
    registered_worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    visual = run['visual_analysis']
    assert visual['result']['available'] and visual['result']['review_score'] is None
    assert visual['result']['metrics']['edge_density'] == 0
    assert not visual['provenance']['cache_hit'] and visual['provenance']['viewport'] is None
    assert run['job']['status'] == 'partial'
    assert run['input_snapshot']['config']['weights']['visual'] == 0
    evidence = client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items']
    image = next(item for item in evidence if item['kind'] == 'image')
    assert client.get(image['image_url']).content == original
    retry = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'visual-retry'}).json()
    registered_worker.run_once()
    second = client.get('/api/v1/runs/' + retry['run_id']).json()['visual_analysis']
    assert second['provenance']['cache_hit'] and second['result']['metrics'] == visual['result']['metrics']
    with pytest.raises(IntegrityError):
        with application.state.database.transaction(immediate=True) as session:
            session.scalar(select(VisualAnalysis)).result = {}


def test_missing_image_has_null_metrics(client, job_lead, registered_worker):
    job = submit(client, job_lead, upload(client, job_lead).json()).json()
    registered_worker.run_once()
    result = client.get('/api/v1/runs/' + job['run_id']).json()['visual_analysis']['result']
    assert result['available'] is False and result['metrics'] is None and result['reason'] == 'IMAGE_MISSING'


def test_rejected_image_makes_history_stale_and_retry_unavailable(client, job_lead, registered_worker):
    job = submit(client, job_lead, upload(client, job_lead, image=screenshot()).json()).json()
    registered_worker.run_once()
    image = next(item for item in client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items'] if item['kind'] == 'image')
    reviewed = client.patch('/api/v1/evidence/' + image['id'] + '/review', json={'usable': False, 'reason': 'Blocked screenshot'}, headers={'If-Match': '"1"'})
    assert reviewed.status_code == 200
    old = client.get('/api/v1/runs/' + job['run_id']).json()
    assert not old['is_current'] and 'EVIDENCE_REVIEW_CHANGED' in old['stale_reasons']
    assert old['visual_analysis']['result']['metrics'] is not None
    retry = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'rejected-retry'}).json()
    registered_worker.run_once()
    result = client.get('/api/v1/runs/' + retry['run_id']).json()['visual_analysis']['result']
    assert not result['available'] and result['metrics'] is None


def test_review_change_before_commit_discards_measurements(client, job_lead, registered_worker, application):
    handler = registered_worker.handlers['visual_metrics']
    def changed(context, snapshot, outputs):
        result = handler(context, snapshot, outputs)
        with application.state.database.transaction(immediate=True) as session:
            evidence = session.get(Evidence, outputs['acquire_image']['evidence_id'])
            evidence.usable = False
            evidence.revision += 1
        return result
    registered_worker.handlers['visual_metrics'] = changed
    job = submit(client, job_lead, upload(client, job_lead, image=screenshot()).json()).json()
    registered_worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert run['visual_analysis'] is None
    assert any(error['code'] == 'IMAGE_REVIEW_CHANGED' for error in run['job']['errors'])


def test_cached_result_still_verifies_original_bytes(client, job_lead, registered_worker, application):
    job = submit(client, job_lead, upload(client, job_lead, image=screenshot()).json()).json()
    registered_worker.run_once()
    handler = registered_worker.handlers['visual_metrics']
    def tampered(context, snapshot, outputs):
        with application.state.database.sessions() as session:
            evidence = session.get(Evidence, outputs['acquire_image']['evidence_id'])
            target = application.state.storage.resolve(evidence.metadata_json['artifact_key'])
        target.write_bytes(b'changed original')
        return handler(context, snapshot, outputs)
    registered_worker.handlers['visual_metrics'] = tampered
    retry = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'tamper-retry'}).json()
    registered_worker.run_once()
    result = client.get('/api/v1/runs/' + retry['run_id']).json()['visual_analysis']['result']
    assert not result['available'] and result['reason'] == 'ARTIFACT_INTEGRITY_ERROR'


def test_configuration_change_invalidates_queued_run(client, job_lead, registered_worker, monkeypatch):
    from app.modules.computer_vision import vision_config
    job = submit(client, job_lead, upload(client, job_lead, image=screenshot()).json()).json()
    identity = vision_config.vision_identity()
    identity['config']['max_width'] = 600
    monkeypatch.setattr(vision_config, 'vision_identity', lambda: identity)
    registered_worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert not run['is_current'] and 'VISION_CONFIG_CHANGED' in run['stale_reasons']
    assert run['visual_analysis'] is None
    assert any(error['code'] == 'INPUT_CHANGED' for error in run['job']['errors'])
