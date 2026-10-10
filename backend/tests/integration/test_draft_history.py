import json
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.modules.outreach.outreach_model import OutreachDraft, OutreachRevision
from app.modules.knowledge.knowledge_schema import RetrievalResponse
from app.modules.nlp import ollama_client
from test_model_failure import nlp_worker, request


@pytest.fixture
def draft_environment(client, job_lead, nlp_worker, monkeypatch):
    worker, calls = nlp_worker
    # Service exists before research so it is part of the pinned research context.
    service = client.post('/api/v1/services', json={'name': 'Connected security systems',
                                                  'description': 'We offer connected security systems.'}).json()
    researched = request(client, job_lead); worker.run_once()
    def retrieve(*args):
        return RetrievalResponse(query_text='Test company', sources=[], empty_reason='NO_RELEVANT_SOURCES',
                                 minimum_similarity=.30, candidate_count=0, excluded_incompatible=0, model={})
    monkeypatch.setattr('app.modules.outreach.outreach_worker.preview', retrieve)
    def generate(context, payload):
        calls.append(payload)
        return json.dumps({'subject': 'Connected security systems',
            'body': 'Hello,\nWe offer connected security systems. Would you be interested in discussing whether this service is relevant?',
            'claims': [{'text': 'We offer connected security systems.', 'source_id': 'service',
                        'quote': 'We offer connected security systems.'}]}), {}
    monkeypatch.setattr(ollama_client, 'generate', generate)
    return worker, service, researched, calls


def generate_draft(client, lead, environment, key='draft'):
    worker, service, _, _ = environment
    response = client.post(f'/api/v1/leads/{lead["id"]}/outreach-jobs',
        json={'service_id': service['id']}, headers={'Idempotency-Key': key})
    assert response.status_code == 202, response.text
    worker.run_once()
    job = client.get(response.json()['poll_url']).json()
    assert job['status'] == 'completed', job
    return client.get('/api/v1/drafts/'+job['result']['draft_id']).json(), response.json()


def review(client, draft, **changes):
    return client.post('/api/v1/drafts/'+draft['id']+'/review', headers={'If-Match': f'"{draft["revision"]}"'},
        json={'decision': 'Approved', 'reviewer': 'Local test reviewer', 'factual_review_acknowledged': True, **changes})


def test_generate_review_copy_edit_preserve_history_and_pipeline(client, job_lead, draft_environment, application):
    draft, receipt = generate_draft(client, job_lead, draft_environment)
    assert draft['current_revision']['state'] == 'Generated'
    assert 'NO_RELEVANT_KNOWLEDGE_SERVICE_ONLY' in draft['warnings']
    assert client.get('/api/v1/drafts/'+draft['id']+'/approved-text').status_code == 409
    assert review(client, draft, factual_review_acknowledged=False).status_code == 422
    approved = review(client, draft).json()
    copied = client.get('/api/v1/drafts/'+draft['id']+'/approved-text').json()
    assert copied['body'] == draft['current_revision']['body'] and copied['sent'] is False
    assert len(approved['history']) == 2 and approved['current_revision']['reviewer'] == 'Local test reviewer'
    assert review(client, draft).status_code == 409  # Concurrent stale revision.
    edited = client.post('/api/v1/drafts/'+draft['id']+'/revisions', headers={'If-Match': '"2"'},
                        json={key: copied[key] for key in ('subject', 'body')} | {'claims': draft['current_revision']['claims']}).json()
    assert edited['current_revision']['state'] == 'Edited'
    assert edited['history'][1]['state'] == 'Approved'
    assert client.get('/api/v1/drafts/'+draft['id']+'/approved-text').status_code == 409
    lead = client.get('/api/v1/leads/'+job_lead['id']).json()
    assert lead['pipeline_state'] == 'New' and lead['latest_job_id'] == draft_environment[2]['job_id']
    with pytest.raises(IntegrityError), application.state.database.transaction(immediate=True) as session:
        session.scalar(select(OutreachRevision)).body = 'Overwrite history'


def test_new_factual_edit_blocks_approval_and_keeps_user_text(client, job_lead, draft_environment):
    draft, _ = generate_draft(client, job_lead, draft_environment)
    current = draft['current_revision']
    edit = client.post('/api/v1/drafts/'+draft['id']+'/revisions', headers={'If-Match': '"1"'},
        json={'subject': current['subject'], 'body': current['body']+' We built a bank alarm system.', 'claims': current['claims']})
    assert edit.status_code == 201
    edited = edit.json()
    assert edited['current_revision']['unresolved_claims']
    assert 'We built a bank alarm system.' in edited['current_revision']['body']
    assert review(client, edited).json()['error']['code'] == 'UNRESOLVED_CLAIMS'


def test_service_change_prevents_approval_and_flags_old_approved_text(client, job_lead, draft_environment):
    draft, _ = generate_draft(client, job_lead, draft_environment)
    approved = review(client, draft).json()
    service = draft_environment[1]
    client.patch('/api/v1/services/'+service['id'], headers={'If-Match': '"1"'}, json={'active': False})
    copied = client.get('/api/v1/drafts/'+draft['id']+'/approved-text').json()
    assert copied['stale_reasons'] == ['Selected service changed', 'Company research is outdated']
    assert review(client, approved).json()['error']['code'] == 'CONTEXT_STALE'


def test_reject_requires_reason_and_regeneration_is_separate(client, job_lead, draft_environment):
    draft, receipt = generate_draft(client, job_lead, draft_environment)
    assert review(client, draft, decision='Rejected', reason=None).status_code == 422
    rejected = review(client, draft, decision='Rejected', reason='Needs a clearer invitation.').json()
    assert rejected['current_revision']['state'] == 'Rejected'
    worker, service, _, _ = draft_environment
    replay = client.post(f'/api/v1/leads/{job_lead["id"]}/outreach-jobs', json={'service_id': service['id']}, headers={'Idempotency-Key': 'draft'})
    assert replay.json()['job_id'] == receipt['job_id']
    assert replay.json()['status'] == 'completed'
    second, _ = generate_draft(client, job_lead, draft_environment, 'regenerate')
    assert second['id'] != draft['id']
    assert len(client.get('/api/v1/leads/'+job_lead['id']+'/drafts').json()['items']) == 2


def test_invalid_generation_budget_uses_only_validated_service_template(client, job_lead, draft_environment, monkeypatch, application):
    worker, service, _, calls = draft_environment
    count = []
    def invalid(context, payload):
        count.append(payload)
        return '{}', {}
    monkeypatch.setattr(ollama_client, 'generate', invalid)
    queued = client.post(f'/api/v1/leads/{job_lead["id"]}/outreach-jobs', json={'service_id': service['id']}, headers={'Idempotency-Key': 'invalid'}).json()
    worker.run_once()
    assert len(count) == 2
    polled = client.get(queued['poll_url']).json()
    assert polled['status'] == 'completed' and polled['result']['draft_id'] is not None
    assert 'TEMPLATE_FALLBACK_MODEL_OUTPUT_INVALID' in polled['warnings']
    assert next(stage for stage in polled['stages'] if stage['name'] == 'retrieve_outreach')['output']['retrieval']
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(OutreachDraft)) == 1
    draft = client.get('/api/v1/drafts/'+polled['result']['draft_id']).json()
    assert draft['provenance']['method'] == 'service_template'
    assert draft['current_revision']['claims'][0]['source_id'] == 'service'
    assert '{}' not in draft['current_revision']['body']


def test_context_change_while_queued_prevents_generation(client, job_lead, draft_environment):
    worker, service, _, calls = draft_environment
    queued = client.post(f'/api/v1/leads/{job_lead["id"]}/outreach-jobs', json={'service_id': service['id']}, headers={'Idempotency-Key': 'stale'}).json()
    client.patch('/api/v1/leads/'+job_lead['id'], headers={'If-Match': '"1"'}, json={'description': 'Changed company description'})
    before = len(calls); worker.run_once()
    job = client.get(queued['poll_url']).json()
    assert job['status'] == 'failed' and len(calls) == before
