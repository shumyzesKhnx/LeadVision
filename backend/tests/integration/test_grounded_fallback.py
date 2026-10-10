import json
import pytest
from app.modules.nlp import ollama_client, model_cache_service
from test_knowledge import agency, knowledge_worker, document, index, patch
from test_leads import setup_campaign, add_lead
from test_model_failure import request, valid_output
from test_draft_history import review


@pytest.fixture
def grounded_environment(client, knowledge_worker, monkeypatch):
    worker, _, embedding_info, _ = knowledge_worker
    monkeypatch.setattr('app.modules.semantics.embedding_config.encoder_config', lambda: embedding_info['identity']['config'])
    info = lambda settings: {'status': 'available', 'digest': 'a' * 64}
    monkeypatch.setattr(model_cache_service, 'model_info', info)
    monkeypatch.setattr(ollama_client, 'model_info', info)
    lead = add_lead(client, setup_campaign(client), description='A bank interested in connected security systems.')
    service = client.post('/api/v1/services', json={'name': 'Connected security systems',
                                                  'description': 'We offer connected security systems.'}).json()
    row = document(client, title='Real home-security experience', demo=False, approved=True,
                   text='We built a connected home-security platform.')
    indexed = index(client, row); assert indexed.status_code == 202, indexed.text
    worker.run_once()
    monkeypatch.setattr(ollama_client, 'generate', lambda *_: (json.dumps(valid_output()), {}))
    request(client, lead); worker.run_once()
    hooks = {'generate': lambda: None}
    def generate(context, payload):
        data = json.loads(payload['prompt'])
        knowledge = next(s for s in data['sources'] if s['kind'] == 'knowledge')
        hooks['generate']()
        return json.dumps({'subject': 'Connected security systems',
            'body': 'Hello,\nWe offer connected security systems. We built a connected home-security platform. Would a conversation be useful?',
            'claims': [{'text': 'We offer connected security systems.', 'source_id': 'service', 'quote': 'We offer connected security systems.'},
                       {'text': knowledge['text'], 'source_id': knowledge['source_id'], 'quote': knowledge['text']}]}), {}
    monkeypatch.setattr(ollama_client, 'generate', generate)
    return worker, lead, service, row, hooks


def queue(client, lead, service, **changes):
    result = client.post('/api/v1/leads/'+lead['id']+'/outreach-jobs',
                        json={'service_id': service['id'], **changes}, headers={'Idempotency-Key': 'grounded'})
    assert result.status_code == 202, result.text
    return result.json()


def test_knowledge_snapshot_archive_retains_approval_with_warning(client, grounded_environment):
    worker, lead, service, row, _ = grounded_environment
    job = queue(client, lead, service); worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert polled['status'] == 'completed', polled
    draft = client.get('/api/v1/drafts/'+polled['result']['draft_id']).json()
    assert draft['retrieval']['sources'][0]['document_id'] == row['id']
    assert not any(s.get('demo') for s in draft['sources'])
    assert review(client, draft).status_code == 201
    patch(client, row, active=False)
    historical = client.get('/api/v1/drafts/'+draft['id']+'/approved-text').json()
    assert 'Agency knowledge changed' in historical['stale_reasons']
    assert 'home-security platform' in historical['body']


def test_knowledge_change_during_generation_discards_draft(client, grounded_environment):
    worker, lead, service, row, hooks = grounded_environment
    hooks['generate'] = lambda: patch(client, row, active=False)
    job = queue(client, lead, service); worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert polled['status'] == 'failed' and polled['result']['draft_id'] is None
    assert any(e['code'] == 'INPUT_CHANGED' for e in polled['errors'])
    assert client.get('/api/v1/leads/'+lead['id']+'/drafts').json()['items'] == []
    assert next(s for s in polled['stages'] if s['name'] == 'retrieve_outreach')['output']['retrieval']['sources']


def test_fictional_knowledge_excluded_from_real_outreach(client, grounded_environment):
    worker, lead, service, _, _ = grounded_environment
    demo = document(client, title='Fictional bank success', text='We built an alarm system for a fictional bank.', demo=True, approved=True)
    assert index(client, demo, key='demo').status_code == 202; worker.run_once()
    job = queue(client, lead, service); worker.run_once()
    polled = client.get(job['poll_url']).json()
    assert polled['status'] == 'completed', polled
    draft = client.get('/api/v1/drafts/'+polled['result']['draft_id']).json()
    assert all(s.get('document_id') != demo['id'] for s in draft['sources'])
