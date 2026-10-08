from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from uuid import uuid4
import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.errors import AppError
from app.models.evidence import Evidence, SavedEvidenceUpload
from app.models.job import Job, JobStage
from app.models.maintenance import FileCleanupTask
from app.services.evidence import housekeeping
from app.services.workflow import StageResult
from app.worker.main import Worker
from test_leads import setup_campaign, add_lead


def screenshot():
    output = BytesIO(); Image.new('RGB', (80, 40), 'green').save(output, format='PNG')
    return output.getvalue()


def upload(client, lead, *, text=b'Example Company builds software for businesses.', image=None, **metadata):
    files = {}
    if text is not None:
        files['text_file'] = ('website.txt', text, 'text/plain')
    if image is not None:
        files['image_file'] = ('screen.png', image, 'image/png')
    return client.post(f"/api/v1/leads/{lead['id']}/saved-evidence", files=files, data=metadata)


def submit(client, lead, receipt, key='saved-1', mode=None):
    return client.post(f"/api/v1/leads/{lead['id']}/analysis-jobs", headers={'Idempotency-Key': key},
                       json={'mode': mode or receipt['source_mode'], 'upload_token': receipt['upload_token']})


def test_saved_offline_pair_provenance_artifacts_and_replay(client, job_lead, registered_worker, application):
    original = screenshot()
    response = upload(client, job_lead, image=original, source_mode='cached', original_url='https://example.com/about',
                      collected_at='2025-01-01T12:00:00+05:00', title='About our company')
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt['text_available'] and receipt['image_available']
    job = submit(client, job_lead, receipt).json()
    assert submit(client, job_lead, receipt).json() == job
    registered_worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert polled['status'] == 'partial' and polled['errors'][0]['stage'] == 'business_analysis'
    evidence = client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()
    assert evidence['total'] == 2
    assert all(item['source_label'] == 'Cached' and item['collected_at'] == '2025-01-01T07:00:00Z' for item in evidence['items'])
    image = next(item for item in evidence['items'] if item['kind'] == 'image')
    downloaded = client.get(image['image_url'])
    assert downloaded.content == original and downloaded.headers['x-content-type-options'] == 'nosniff'
    assert client.get(image['thumbnail_url']).headers['content-type'] == 'image/jpeg'
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert 'upload_token' not in run['input_snapshot']['request']
    assert 'artifact_key' not in str(run) and 'thumbnail_key' not in str(evidence)
    assert submit(client, job_lead, receipt, key='new').json()['error']['code'] == 'UPLOAD_CONSUMED'


@pytest.mark.parametrize('text,image,expected', [(b'Some text', None, 'text'), (None, screenshot(), 'image'),
    (b'Some text', b'fake image', 'text')], ids=['text-only', 'image-only', 'invalid-image-keeps-text'])
def test_missing_or_invalid_component_keeps_other_evidence(client, job_lead, registered_worker, text, image, expected):
    receipt = upload(client, job_lead, text=text, image=image).json()
    assert receipt[expected + '_available']
    job = submit(client, job_lead, receipt).json()
    registered_worker.run_once()
    items = client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items']
    assert len(items) == 1 and items[0]['kind'] == expected and items[0]['collected_at'] is None
    assert client.get(job['poll_url']).json()['status'] == 'partial'


def test_bad_text_empty_upload_metadata_and_size_write_no_manifest(client, job_lead, application):
    path = f"/api/v1/leads/{job_lead['id']}/saved-evidence"
    assert client.post(path).status_code == 422
    assert upload(client, job_lead, text=b'\xff').status_code == 422
    assert upload(client, job_lead, text=b' ').status_code == 422
    assert upload(client, job_lead, collected_at='2025-01-01T12:00:00').status_code == 422
    assert upload(client, job_lead, original_url='http://127.0.0.1/private').status_code == 422
    assert upload(client, job_lead, text=b'x' * 1_000_001).status_code == 413
    assert upload(client, job_lead, text=None, image=b'invalid').status_code == 422
    assert client.post(path, content=b'x', headers={'Content-Type': 'multipart/form-data; boundary=test',
                                                 'Content-Length': '11065537'}).status_code == 413
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(SavedEvidenceUpload)) == 0


def test_manifest_survives_api_restart(client, job_lead, application, settings, registered_worker):
    receipt = upload(client, job_lead).json()
    restarted = create_app(settings)
    with TestClient(restarted, base_url='http://127.0.0.1:8000') as second:
        assert submit(second, job_lead, receipt).status_code == 202
    registered_worker.run_once()
    assert client.get('/api/v1/leads/' + job_lead['id'] + '/runs').json()['total'] == 1


def test_ownership_mode_and_atomic_attachment(client, job_lead, registered_worker, application, monkeypatch):
    receipt = upload(client, job_lead).json()
    campaign = client.get('/api/v1/campaigns/' + job_lead['campaign_id']).json()
    other = add_lead(client, campaign, website='https://other.example.com')
    assert submit(client, other, receipt).json()['error']['code'] == 'UPLOAD_NOT_FOUND'
    assert submit(client, job_lead, receipt, mode='cached').status_code == 422
    from app.services import jobs
    original = jobs.record_activity
    def fail(*args, **kwargs):
        raise AppError('TEST_TRANSACTION_FAILURE', 'Injected transaction failure.', 503)
    monkeypatch.setattr(jobs, 'record_activity', fail)
    assert submit(client, job_lead, receipt).status_code == 503
    monkeypatch.setattr(jobs, 'record_activity', original)
    with application.state.database.sessions() as session:
        manifest = session.scalar(select(SavedEvidenceUpload))
        assert manifest.state == 'ready' and manifest.attached_job_id is None
        assert session.scalar(select(func.count()).select_from(Job)) == 0
    assert submit(client, job_lead, receipt).status_code == 202


def test_expiry_abandoned_staging_and_cleanup(client, job_lead, application, registered_worker):
    receipt = upload(client, job_lead).json()
    database, storage = application.state.database, application.state.storage
    with database.transaction(immediate=True) as session:
        manifest = session.scalar(select(SavedEvidenceUpload))
        keys = [manifest.manifest['text']['artifact_key']]
        # Simulate an expired reservation before becoming ready; provenance stays immutable normally.
        session.connection().exec_driver_sql('DROP TRIGGER saved_evidence_ready_no_update')
        manifest.expires_at = '2000-01-01T00:00:00Z'
        target = storage.resolve(keys[0])
        temporary = target.parent / f'.staged-{target.stem}-crashed'
        temporary.write_bytes(b'partial write')
    assert submit(client, job_lead, receipt).json()['error']['code'] == 'UPLOAD_EXPIRED'
    housekeeping(database, storage)
    assert not storage.resolve(keys[0]).exists() and not temporary.exists()
    with database.sessions() as session:
        assert session.scalar(select(SavedEvidenceUpload)).state == 'expired'
        assert all(task.state == 'completed' for task in session.scalars(select(FileCleanupTask)))


def test_review_revision_history_and_retry_preserve_rejection(client, job_lead, registered_worker):
    receipt = upload(client, job_lead, image=screenshot()).json()
    job = submit(client, job_lead, receipt).json(); registered_worker.run_once()
    image = next(item for item in client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items'] if item['kind'] == 'image')
    path = '/api/v1/evidence/' + image['id'] + '/review'
    assert client.patch(path, json={'usable': False, 'reason': 'Blocked screenshot'}).status_code == 428
    assert client.patch(path, json={'usable': False}, headers={'If-Match': '"1"'}).status_code == 422
    reviewed = client.patch(path, json={'usable': False, 'reason': 'Blocked screenshot'}, headers={'If-Match': '"1"'})
    assert reviewed.status_code == 200 and reviewed.json()['revision'] == 2
    assert client.patch(path, json={'usable': True}, headers={'If-Match': '"1"'}).status_code == 409
    assert 'EVIDENCE_REVIEW_CHANGED' in client.get('/api/v1/runs/' + job['run_id']).json()['stale_reasons']
    retried = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'retry'}).json()
    registered_worker.run_once()
    copied = next(item for item in client.get('/api/v1/runs/' + retried['run_id'] + '/evidence').json()['items'] if item['kind'] == 'image')
    assert not copied['usable'] and copied['review_reason'] == 'Blocked screenshot'
    stage = next(item for item in client.get(retried['poll_url']).json()['stages'] if item['name'] == 'acquire_image')
    assert not stage['usable'] and not stage['output']['available']


def test_integrity_checks_and_lead_delete_cleanup(client, job_lead, registered_worker, application):
    receipt = upload(client, job_lead, image=screenshot()).json()
    job = submit(client, job_lead, receipt).json(); registered_worker.run_once()
    database, storage = application.state.database, application.state.storage
    with database.sessions() as session:
        image = session.scalar(select(Evidence).where(Evidence.kind == 'image'))
        image_id = image.id
        key = image.metadata_json['artifact_key']
        manifest = session.scalar(select(SavedEvidenceUpload)).manifest
        keys = [manifest['text']['artifact_key'], key, manifest['image']['thumbnail_key']]
    storage.resolve(key).write_bytes(b'tampered')
    assert client.get('/api/v1/artifacts/' + image_id + '/image').json()['error']['code'] == 'ARTIFACT_INTEGRITY_ERROR'
    assert client.get('/api/v1/artifacts/' + str(uuid4()) + '/image').status_code == 404
    deletion = client.delete('/api/v1/leads/' + job_lead['id'] + '?confirm=true', headers={'If-Match': '"1"'})
    assert deletion.status_code == 202 and deletion.json()['cleanup']['tasks'] == 3
    assert client.get('/api/v1/artifacts/' + image_id + '/image').status_code == 404
    housekeeping(database, storage)
    assert all(not storage.resolve(key).exists() for key in keys)
    with database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Evidence)) == 0
        assert session.scalar(select(func.count()).select_from(SavedEvidenceUpload)) == 0


def test_evidence_stage_and_activity_rollback_together(client, job_lead, registered_worker, application, monkeypatch):
    receipt = upload(client, job_lead).json(); job = submit(client, job_lead, receipt).json()
    import app.worker.main as module
    original = module.record_activity
    def fail(session, **kwargs):
        if kwargs.get('new_value', {}).get('stage') == 'acquire_text':
            raise RuntimeError('Injected stage commit failure')
        return original(session, **kwargs)
    monkeypatch.setattr(module, 'record_activity', fail)
    registered_worker.run_once()
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Evidence)) == 0
        stage = session.scalar(select(JobStage).where(JobStage.job_id == job['job_id'], JobStage.name == 'acquire_text'))
        assert stage.output is None and not stage.usable


def test_source_records_are_immutable(client, job_lead, registered_worker, application):
    receipt = upload(client, job_lead).json(); submit(client, job_lead, receipt); registered_worker.run_once()
    with pytest.raises(IntegrityError):
        with application.state.database.transaction(immediate=True) as session:
            session.scalar(select(Evidence)).source_mode = 'cached'
    with pytest.raises(IntegrityError):
        with application.state.database.transaction(immediate=True) as session:
            session.scalar(select(SavedEvidenceUpload)).manifest = {}


def test_unavailable_worker_leaves_token_ready(client, job_lead, application, settings):
    receipt = upload(client, job_lead).json()
    assert submit(client, job_lead, receipt).json()['error']['code'] == 'WORKER_UNAVAILABLE'
    with application.state.database.sessions() as session:
        assert session.scalar(select(SavedEvidenceUpload)).state == 'ready'
    with Worker(application.state.database, settings):
        assert submit(client, job_lead, receipt).status_code == 202


def test_competing_keys_cannot_consume_upload_twice(client, job_lead, registered_worker, settings, application):
    settings.sqlite_busy_timeout_ms = 2000
    receipt = upload(client, job_lead).json()
    gate = Barrier(2)
    def post(key):
        gate.wait()
        return submit(client, job_lead, receipt, key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(post, ['one', 'two']))
    assert sorted(item.status_code for item in results) == [202, 409]
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_failed_artifact_write_has_durable_cleanup(client, job_lead, application, monkeypatch):
    storage, database = application.state.storage, application.state.database
    original = storage.write_to
    attempts = 0
    def fail(key, content, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError('Simulated disk failure with a private path')
        return original(key, content, **kwargs)
    monkeypatch.setattr(storage, 'write_to', fail)
    result = upload(client, job_lead, image=screenshot())
    assert result.status_code == 503 and 'private path' not in result.text
    with database.sessions() as session:
        manifest = session.scalar(select(SavedEvidenceUpload))
        assert manifest.state == 'expired'
        assert session.scalar(select(func.count()).select_from(FileCleanupTask)) == 3
    housekeeping(database, storage)
    assert not list((storage.root / 'evidence').glob('*.txt'))


def test_corrupt_screenshot_warns_without_losing_text(client, job_lead, registered_worker, application):
    receipt = upload(client, job_lead, image=screenshot()).json()
    with application.state.database.sessions() as session:
        manifest = session.scalar(select(SavedEvidenceUpload)).manifest
    application.state.storage.resolve(manifest['image']['artifact_key']).write_bytes(b'changed')
    job = submit(client, job_lead, receipt).json(); registered_worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert polled['errors'][0]['stage'] == 'business_analysis' and polled['status'] == 'partial'
    image = next(stage for stage in polled['stages'] if stage['name'] == 'acquire_image')
    assert image['state'] == 'warning' and not image['usable']
    items = client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items']
    assert next(item for item in items if item['kind'] == 'text')['usable']
    assert not next(item for item in items if item['kind'] == 'image')['usable']


def test_chunked_upload_is_bounded_before_parsing(client, job_lead):
    def body():
        yield b'--boundary\r\nContent-Disposition: form-data; name="image_file"; filename="screen.png"\r\n\r\n'
        yield b'x' * 11_100_000
        yield b'\r\n--boundary--\r\n'
    response = client.post('/api/v1/leads/' + job_lead['id'] + '/saved-evidence', content=body(),
                           headers={'Content-Type': 'multipart/form-data; boundary=boundary'})
    assert response.status_code == 413 and response.json()['error']['code'] == 'EVIDENCE_TOO_LARGE'
