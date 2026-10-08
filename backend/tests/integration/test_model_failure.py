import json
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models.business_analysis import BusinessAnalysis, ModelDiagnostic
from app.services.workflow import StageFailure, StageResult
from app.worker.main import Worker
from app.services import model_cache
from app.integrations import ollama_client
from test_saved_evidence import upload, submit
TEXT = 'CloudBooks provides accounting software to small businesses.'


def valid_output():
    return {'summary': TEXT, 'summary_sources': [{'source_id': 'website_text', 'quote': TEXT}],
            'industry': None, 'products': [{'value': 'accounting software', 'source_id': 'website_text', 'quote': TEXT}],
            'markets': [], 'employee_count': None, 'opportunities': []}


@pytest.fixture
def nlp_worker(client, application, settings, monkeypatch):
    info = lambda settings: {'status': 'available', 'digest': 'a' * 64}
    monkeypatch.setattr(model_cache, 'model_info', info)
    monkeypatch.setattr(ollama_client, 'model_info', info)
    calls = []
    def generate(context, payload):
        calls.append(payload)
        return json.dumps(valid_output()), {'prompt_eval_count': 100, 'eval_count': 80}
    monkeypatch.setattr(ollama_client, 'generate', generate)
    with Worker(application.state.database, settings) as worker:
        yield worker, calls


def request(client, lead):
    return submit(client, lead, upload(client, lead, text=TEXT.encode()).json()).json()


def test_nlp_source_linked_result_cache_and_no_lead_overwrite(client, job_lead, nlp_worker, application):
    worker, calls = nlp_worker
    job = request(client, job_lead); worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert run['business_analysis']['result']['employee_count'] is None
    assert run['business_analysis']['provenance']['model']['digest'] == 'a' * 64
    assert run['job']['errors'][0]['stage'] == 'visual_metrics'
    assert client.get('/api/v1/leads/' + job_lead['id']).json()['revision'] == 1
    retried = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'retry'}).json()
    worker.run_once()
    second = client.get('/api/v1/runs/' + retried['run_id']).json()
    assert second['business_analysis']['provenance']['cache_hit'] and len(calls) == 1
    with pytest.raises(IntegrityError):
        with application.state.database.transaction(immediate=True) as session:
            session.scalar(select(BusinessAnalysis)).result = {}


def test_one_repair_and_invalid_output_retains_bounded_diagnostic(client, job_lead, nlp_worker, application, monkeypatch):
    worker, calls = nlp_worker
    def invalid(context, payload):
        calls.append(payload)
        return '{"secret_extra_key":"invalid"}', {}
    monkeypatch.setattr(ollama_client, 'generate', invalid)
    job = request(client, job_lead); worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert len(calls) == 2 and 'secret_extra_key' not in str(polled)
    assert any(error['code'] == 'MODEL_OUTPUT_INVALID' for error in polled['errors'])
    with application.state.database.sessions() as session:
        diagnostic = session.scalar(select(ModelDiagnostic))
        assert application.state.storage.resolve(diagnostic.artifact_key).read_text() == '{"secret_extra_key":"invalid"}'
        assert session.scalar(select(func.count()).select_from(BusinessAnalysis)) == 0


def test_transport_retry_and_repair_share_two_call_budget(client, job_lead, nlp_worker, monkeypatch):
    worker, calls = nlp_worker
    def response(context, payload):
        calls.append(payload)
        if len(calls) == 1: raise StageFailure('MODEL_UNAVAILABLE', retryable=True)
        return '{}', {}
    monkeypatch.setattr(ollama_client, 'generate', response)
    job = request(client, job_lead); worker.run_once()
    assert len(calls) == 2
    assert any(error['code'] == 'MODEL_OUTPUT_INVALID' for error in client.get(job['poll_url']).json()['errors'])


def test_successful_repair_is_recorded(client, job_lead, nlp_worker, monkeypatch):
    worker, calls = nlp_worker
    def response(context, payload):
        calls.append(payload)
        return ('{}' if len(calls) == 1 else json.dumps(valid_output())), {}
    monkeypatch.setattr(ollama_client, 'generate', response)
    job = request(client, job_lead); worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert len(calls) == 2 and 'MODEL_OUTPUT_REPAIRED' in polled['warnings']


def test_model_change_is_fenced_and_independent_visual_stage_runs(client, job_lead, nlp_worker, monkeypatch):
    worker, calls = nlp_worker
    job = request(client, job_lead)
    monkeypatch.setattr(ollama_client, 'model_info', lambda settings: {'status': 'available', 'digest': 'b' * 64})
    worker.handlers['visual_metrics'] = lambda *args: StageResult(output={'independent_visual': True}, usable=True)
    worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert not calls and any(error['code'] == 'MODEL_CHANGED' for error in polled['errors'])
    assert next(stage for stage in polled['stages'] if stage['name'] == 'visual_metrics')['state'] == 'succeeded'


def test_manual_change_invalidates_cache(client, job_lead, nlp_worker):
    worker, calls = nlp_worker
    job = request(client, job_lead); worker.run_once()
    client.patch('/api/v1/leads/' + job_lead['id'], json={'employee_count': 12}, headers={'If-Match': '"1"'})
    retry = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'retry'}).json()
    worker.run_once()
    analysis = client.get('/api/v1/runs/' + retry['run_id']).json()['business_analysis']
    assert len(calls) == 2 and not analysis['provenance']['cache_hit']
    assert analysis['result']['employee_count']['source_id'] == 'manual:employee_count'


def test_evidence_review_during_generation_discards_result(client, job_lead, nlp_worker, monkeypatch):
    worker, calls = nlp_worker
    def response(context, payload):
        with worker.database.sessions() as session:
            from app.models.evidence import Evidence
            evidence = session.scalar(select(Evidence))
            evidence_id = evidence.id
        client.patch('/api/v1/evidence/' + evidence_id + '/review', json={'usable': False, 'reason': 'Incorrect text'}, headers={'If-Match': '"1"'})
        return json.dumps(valid_output()), {}
    monkeypatch.setattr(ollama_client, 'generate', response)
    job = request(client, job_lead); worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert run['business_analysis'] is None
    assert any(error['code'] == 'EVIDENCE_CHANGED' for error in run['job']['errors'])
