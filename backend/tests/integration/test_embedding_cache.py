import hashlib
import numpy as np
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.modules.semantics.embedding_config import encoder_config
from app.modules.semantics.embedding_model import Embedding, EmbeddingRuntime
from app.modules.semantics import embedding_model_client as embedding_model
from app.modules.processing.worker_main import Worker
from test_saved_evidence import upload, submit


@pytest.fixture
def semantic_worker(client, application, settings, monkeypatch):
    identity = {'model': 'test-only-model', 'revision': 'a' * 40, 'config': encoder_config()}
    calls = []
    class Encoder:
        def __init__(self): self.identity = identity
        def select(self, text):
            return {'input_hash': hashlib.sha256(text.strip().encode()).hexdigest(), 'selected_text': text,
                'input_ids': [1, 2], 'token_count': 2, 'truncated': False}
        def encode(self, selection, checkpoint):
            calls.append(selection['input_hash']); checkpoint()
            value = np.zeros(384, dtype=np.float32); value[0] = 1
            return value
    info = {'status': 'available', 'identity': identity}
    monkeypatch.setattr(embedding_model, 'model_info', lambda settings: info)
    monkeypatch.setattr('app.modules.semantics.semantic_matching_service.model_info', lambda settings: info)
    monkeypatch.setattr('app.modules.semantics.semantic_matching_service.get_encoder', lambda worker, identity: Encoder())
    with Worker(application.state.database, settings) as worker: yield worker, calls, info


def start(client, lead, key='semantic'):
    receipt = upload(client, lead, text=b'Example Company provides accounting software.').json()
    return submit(client, lead, receipt, key=key).json()


def retry(client, job, key):
    response = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': key})
    assert response.status_code == 202, response.text
    return response.json()


def test_semantics_fallback_cache_and_immutable_float32_storage(client, job_lead, semantic_worker, application):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    result = run['semantic_result']
    assert result['result']['available'] and result['result']['normalized_similarity'] == 100
    assert result['provenance']['company_source']['source'] == 'bounded_website_text'
    assert len(calls) == 2 and run['job']['status'] == 'partial'
    second = retry(client, job, 'repeat'); worker.run_once()
    repeated = client.get('/api/v1/runs/' + second['run_id']).json()['semantic_result']
    assert len(calls) == 2 and repeated['provenance']['company_cache_hit'] and repeated['provenance']['icp_cache_hit']
    with application.state.database.sessions() as session:
        rows = list(session.scalars(select(Embedding)))
        assert len(rows) == 2 and all(len(row.vector) == 1536 for row in rows)
    with pytest.raises(IntegrityError):
        with application.state.database.transaction(immediate=True) as session:
            session.scalar(select(Embedding)).vector = b'x' * 1536


def test_structured_edit_keeps_vectors_but_description_edit_changes_company_vector(client, job_lead, semantic_worker):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    response = client.patch('/api/v1/leads/' + job_lead['id'], json={'industry': 'Construction'}, headers={'If-Match': '"1"'})
    assert response.status_code == 200
    second = retry(client, job, 'industry'); worker.run_once()
    assert len(calls) == 2
    response = client.patch('/api/v1/leads/' + job_lead['id'], json={'description': 'Entered company description.'}, headers={'If-Match': '"2"'})
    assert response.status_code == 200
    third = retry(client, second, 'description'); worker.run_once()
    result = client.get('/api/v1/runs/' + third['run_id']).json()['semantic_result']
    assert len(calls) == 3 and result['provenance']['company_source']['source'] == 'manual_description'
    assert not client.get('/api/v1/runs/' + job['run_id']).json()['is_current']


def test_missing_model_has_null_similarity_and_keeps_text(client, job_lead, registered_worker):
    job = start(client, job_lead); registered_worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert not run['semantic_result']['result']['available']
    assert run['semantic_result']['result']['raw_cosine'] is None
    assert run['semantic_result']['result']['reason'] == 'EMBEDDING_UNAVAILABLE'
    assert run['job']['status'] == 'partial'


def test_embedding_model_change_marks_history_stale(client, job_lead, semantic_worker, application):
    worker, calls, info = semantic_worker
    job = start(client, job_lead); worker.run_once()
    with application.state.database.transaction(immediate=True) as session:
        row = session.get(EmbeddingRuntime, 1)
        row.identity = {**info['identity'], 'revision': 'b' * 40}
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert not run['is_current'] and 'EMBEDDING_MODEL_CHANGED' in run['stale_reasons']


def test_corrupt_cached_vector_is_not_used(client, job_lead, semantic_worker, application):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    # Frozen rows cannot be changed through the API. Simulate corrupted disk/DB bytes explicitly.
    with application.state.database.engine.begin() as connection:
        connection.exec_driver_sql('DROP TRIGGER embeddings_no_update')
        connection.exec_driver_sql('UPDATE embeddings SET vector=?', (np.full(384, np.nan, dtype='<f4').tobytes(),))
    next_job = retry(client, job, 'corrupt'); worker.run_once()
    run = client.get('/api/v1/runs/' + next_job['run_id']).json()
    assert not run['semantic_result']['result']['available']
    assert run['semantic_result']['result']['reason'] == 'NONFINITE_VECTOR'


def test_delete_lead_removes_only_unreferenced_company_vectors(client, job_lead, semantic_worker, application):
    from test_leads import add_lead
    worker, calls, _ = semantic_worker
    first = start(client, job_lead); worker.run_once()
    second_lead = add_lead(client, {'id': job_lead['campaign_id']}, company_name='Second Company', website='https://second.example.com')
    second = start(client, second_lead, 'second'); worker.run_once()
    assert len(calls) == 2
    assert client.delete('/api/v1/leads/' + job_lead['id'] + '?confirm=true', headers={'If-Match': '"1"'}).status_code == 202
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Embedding)) == 2
    assert client.delete('/api/v1/leads/' + second_lead['id'] + '?confirm=true', headers={'If-Match': '"1"'}).status_code == 202
    with application.state.database.sessions() as session:
        remaining = list(session.scalars(select(Embedding)))
        assert len(remaining) == 1 and remaining[0].purpose == 'icp'


def test_target_change_recomputes_only_icp_vector(client, job_lead, semantic_worker):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    campaign = client.get('/api/v1/campaigns/' + job_lead['campaign_id']).json()
    changed = client.patch('/api/v1/icps/' + campaign['icp_id'], json={'target_text': 'Construction companies needing bridge planning.'}, headers={'If-Match': '"1"'})
    assert changed.status_code == 200, changed.text
    assert not client.get('/api/v1/runs/' + job['run_id']).json()['is_current']
    second = retry(client, job, 'new-target'); worker.run_once()
    result = client.get('/api/v1/runs/' + second['run_id']).json()['semantic_result']
    assert len(calls) == 3 and result['provenance']['company_cache_hit'] and not result['provenance']['icp_cache_hit']


def test_rejected_text_is_not_used_on_retry(client, job_lead, semantic_worker):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    text = client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items'][0]
    reviewed = client.patch('/api/v1/evidence/' + text['id'] + '/review', json={'usable': False, 'reason': 'Incorrect company text'}, headers={'If-Match': '"1"'})
    assert reviewed.status_code == 200
    second = retry(client, job, 'rejected-text'); worker.run_once()
    result = client.get('/api/v1/runs/' + second['run_id']).json()['semantic_result']['result']
    assert not result['available'] and result['raw_cosine'] is None and len(calls) == 2


def test_preference_edit_changes_only_target_vector(client, job_lead, semantic_worker):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    campaign = client.get('/api/v1/campaigns/' + job_lead['campaign_id']).json()
    changed = client.patch('/api/v1/icps/' + campaign['icp_id'], json={'preferences_text': 'Prefer companies in Pakistan'}, headers={'If-Match': '"1"'})
    assert changed.status_code == 200, changed.text
    second = retry(client, job, 'preferences'); worker.run_once()
    result = client.get('/api/v1/runs/' + second['run_id']).json()['semantic_result']
    assert len(calls) == 3 and result['provenance']['company_cache_hit'] and not result['provenance']['icp_cache_hit']


def test_target_change_recomputes_only_icp_vector(client, job_lead, semantic_worker):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    campaign = client.get('/api/v1/campaigns/' + job_lead['campaign_id']).json()
    changed = client.patch('/api/v1/icps/' + campaign['icp_id'], json={'target_text': 'Construction companies needing bridge planning.'}, headers={'If-Match': '"1"'})
    assert changed.status_code == 200, changed.text
    assert not client.get('/api/v1/runs/' + job['run_id']).json()['is_current']
    second = retry(client, job, 'new-target'); worker.run_once()
    result = client.get('/api/v1/runs/' + second['run_id']).json()['semantic_result']
    assert len(calls) == 3 and result['provenance']['company_cache_hit'] and not result['provenance']['icp_cache_hit']


def test_rejected_text_is_not_used_on_retry(client, job_lead, semantic_worker):
    worker, calls, _ = semantic_worker
    job = start(client, job_lead); worker.run_once()
    text = client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['items'][0]
    reviewed = client.patch('/api/v1/evidence/' + text['id'] + '/review', json={'usable': False, 'reason': 'Incorrect company text'}, headers={'If-Match': '"1"'})
    assert reviewed.status_code == 200
    second = retry(client, job, 'rejected-text'); worker.run_once()
    result = client.get('/api/v1/runs/' + second['run_id']).json()['semantic_result']['result']
    assert not result['available'] and result['raw_cosine'] is None and len(calls) == 2
