import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.modules.scoring.score_model import ScoreRun, ScoreComponent
from app.modules.scoring.reviewer_override_model import ReviewerOverride
from test_embedding_cache import semantic_worker
from test_saved_evidence import upload, submit


def start(client, lead, worker, key='score-test'):
    receipt = upload(client, lead).json()
    job = submit(client, lead, receipt, key=key).json(); worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert run['score_result'] is not None, run
    return job, run['score_result']


def enter_facts(client, lead, **values):
    result = client.patch('/api/v1/leads/' + lead['id'], json=values, headers={'If-Match': f'"{lead["revision"]}"'})
    assert result.status_code == 200, result.text
    return result.json()


def decision(client, lead, score, kind='priority', value='Low', **changes):
    body = {'score_id': score['id'], 'kind': kind, 'value': value, 'reason': 'Reviewed by the agency owner', 'reviewer': 'Owner', **changes}
    return client.post('/api/v1/leads/' + lead['id'] + '/overrides', json=body, headers={'If-Match': f'"{lead["revision"]}"'})


def test_structured_partial_score_history_list_and_stale_suppression(client, job_lead, registered_worker, application):
    lead = enter_facts(client, job_lead, industry='software', country='GB', employee_count=30)
    job, score = start(client, lead, registered_worker)
    assert score['score'] == 100 and score['coverage'] == .6 and score['priority'] == 'High'
    assert score['recommended_for_qualification'] and not score['ineligible']
    detail = client.get('/api/v1/leads/' + lead['id']).json()
    assert detail['score_id'] == score['id'] and len(detail['score_components']) == 5 and detail['pipeline_state'] == 'New'
    assert client.get('/api/v1/leads?priority=High&sort=score&page_size=1').json()['total'] == 1
    assert client.get('/api/v1/leads/' + lead['id'] + '/scores').json()['total'] == 1
    changed = enter_facts(client, lead, employee_count=200)
    assert changed['invalidation']['affected_results'] == 1
    historical = client.get('/api/v1/scores/' + score['id']).json()
    assert historical['score'] == 100 and not historical['is_current'] and historical['priority'] == 'Needs review'
    assert not historical['recommended_for_qualification']
    assert client.get('/api/v1/leads?priority=High').json()['total'] == 0
    response = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'recompute'})
    assert response.status_code == 202, response.text
    registered_worker.run_once()
    second = client.get('/api/v1/runs/' + response.json()['run_id']).json()['score_result']
    assert second['score'] == 75 and second['is_current']
    with pytest.raises(IntegrityError):
        with application.state.database.transaction(immediate=True) as session:
            session.get(ScoreRun, score['id']).result = {}
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ScoreComponent)) == 10


def test_high_semantic_fit_does_not_override_excluded_country(client, job_lead, semantic_worker):
    campaign = client.get('/api/v1/campaigns/' + job_lead['campaign_id']).json()
    changed = client.patch('/api/v1/icps/' + campaign['icp_id'], json={'exclusions': {'countries': ['GB']}}, headers={'If-Match': '"1"'})
    assert changed.status_code == 200
    lead = enter_facts(client, job_lead, industry='software', country='GB', employee_count=30)
    _, score = start(client, lead, semantic_worker[0])
    assert score['score'] == 100 and score['coverage'] == 1 and score['ineligible']
    assert score['exclusion_reasons'][0]['fact'] == 'GB' and not score['recommended_for_qualification']
    result = decision(client, lead, score, 'exclusion', 'allow')
    assert result.status_code == 201, result.text
    assert result.json()['exclusion_override'] and result.json()['ineligible']
    assert not result.json()['recommended_for_qualification']


def test_override_history_clear_reasons_and_changed_inputs(client, job_lead, registered_worker):
    lead = enter_facts(client, job_lead, industry='software', country='GB', employee_count=30)
    _, score = start(client, lead, registered_worker)
    invalid = decision(client, lead, score, reason=' ')
    assert invalid.status_code == 422
    result = decision(client, lead, score)
    assert result.status_code == 201 and result.json()['reviewer_priority'] == 'Low'
    assert result.json()['priority'] == 'High' and result.json()['score'] == 100
    cleared = decision(client, lead, score, value='clear').json()
    assert cleared['reviewer_priority'] is None and len(cleared['overrides']) == 2
    decision(client, lead, score)
    changed = enter_facts(client, lead, country='PK')
    historical = client.get('/api/v1/scores/' + score['id']).json()
    assert historical['reviewer_priority'] is None and not any(item['active'] for item in historical['overrides'])
    assert decision(client, changed, score).status_code == 409
    explicit = decision(client, changed, score, 'qualification', 'allow')
    assert explicit.status_code == 201 and explicit.json()['qualification_override']
    assert not explicit.json()['recommended_for_qualification']
    assert client.get('/api/v1/leads/' + lead['id']).json()['pipeline_state'] == 'New'


def test_custom_threshold_version_and_missing_score(client, job_lead, registered_worker):
    lead = enter_facts(client, job_lead, industry='software', country='GB', employee_count=30)
    job, score = start(client, lead, registered_worker)
    campaign = client.get('/api/v1/campaigns/' + lead['campaign_id']).json()
    changed = client.patch('/api/v1/icps/' + campaign['icp_id'], json={'thresholds': {'high': 80, 'medium': 55, 'minimum_coverage': .8}}, headers={'If-Match': '"1"'})
    assert changed.status_code == 200
    assert changed.json()['invalidation']['affected_results'] == 1
    result = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'thresholds'})
    assert result.status_code == 202
    registered_worker.run_once()
    second = client.get('/api/v1/runs/' + result.json()['run_id']).json()['score_result']
    assert second['thresholds']['minimum_coverage'] == .8 and second['priority'] == 'Needs review'
    assert client.get('/api/v1/scores/' + score['id']).json()['thresholds']['minimum_coverage'] == .6


def test_score_components_overrides_and_shared_vectors_delete_with_lead(client, job_lead, registered_worker, application):
    lead = enter_facts(client, job_lead, industry='software')
    _, score = start(client, lead, registered_worker)
    assert score['score'] == 100 and score['coverage'] == .25 and not score['recommended_for_qualification']
    assert decision(client, lead, score).status_code == 201
    deleted = client.delete('/api/v1/leads/' + lead['id'] + '?confirm=true', headers={'If-Match': f'"{lead["revision"]}"'})
    assert deleted.status_code == 202
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ScoreRun)) == 0
        assert session.scalar(select(func.count()).select_from(ScoreComponent)) == 0
        assert session.scalar(select(func.count()).select_from(ReviewerOverride)) == 0


def test_all_missing_score_and_completed_retry(client, job_lead, registered_worker):
    from test_saved_evidence import screenshot
    receipt = upload(client, job_lead, text=None, image=screenshot()).json()
    job = submit(client, job_lead, receipt).json()
    registered_worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert run['job']['status'] == 'completed'
    score = run['score_result']
    assert score['score'] is None and score['coverage'] == 0 and score['priority'] == 'Needs review'
    assert not score['recommended_for_qualification']
    retried = client.post('/api/v1/jobs/' + job['job_id'] + '/retry', json={}, headers={'Idempotency-Key': 'completed-retry'})
    assert retried.status_code == 202
    registered_worker.run_once()
    assert client.get('/api/v1/leads/' + job_lead['id'] + '/scores').json()['total'] == 2
    assert 'SUPERSEDED_SCORE' in client.get('/api/v1/scores/' + score['id']).json()['stale_reasons']


def test_score_persistence_failure_rolls_back_components_and_activity(client, job_lead, registered_worker, application, monkeypatch):
    from app.modules.processing import activity_service as activity
    from app.modules.processing.activity_model import Activity
    original = activity.record_activity
    def broken(session, **values):
        if values['action'] == 'score.calculated': raise RuntimeError('Simulated commit failure')
        return original(session, **values)
    monkeypatch.setattr(activity, 'record_activity', broken)
    lead = enter_facts(client, job_lead, industry='software')
    receipt = upload(client, lead).json()
    job = submit(client, lead, receipt).json()
    registered_worker.run_once()
    run = client.get('/api/v1/runs/' + job['run_id']).json()
    assert run['score_result'] is None
    assert any(error['stage'] == 'score' for error in run['job']['errors'])
    assert client.get('/api/v1/runs/' + job['run_id'] + '/evidence').json()['total'] == 1
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ScoreRun)) == 0
        assert session.scalar(select(func.count()).select_from(ScoreComponent)) == 0
        assert session.scalar(select(func.count()).select_from(Activity).where(Activity.action == 'score.calculated')) == 0


def test_score_sorting_and_priority_filter_before_pagination(client, job_lead, registered_worker):
    from test_leads import add_lead
    high = enter_facts(client, job_lead, industry='software', country='GB', employee_count=30)
    _, score = start(client, high, registered_worker, key='high')
    low = add_lead(client, {'id': high['campaign_id']}, company_name='Low Fit', website='https://low.example.com')
    low = enter_facts(client, low, industry='construction', country='PK', employee_count=200)
    start(client, low, registered_worker, key='low')
    add_lead(client, {'id': high['campaign_id']}, company_name='Not Scored', website='https://missing.example.com')
    assert client.get('/api/v1/leads?sort=score&page_size=1').json()['items'][0]['id'] == high['id']
    assert client.get('/api/v1/leads?sort=score&direction=asc&page_size=1').json()['items'][0]['id'] == low['id']
    missing = client.get('/api/v1/leads?sort=score&page_size=1&page=3').json()
    assert missing['total'] == 3 and missing['items'][0]['score'] is None
    assert client.get('/api/v1/leads?priority=High&page_size=1').json()['total'] == 1
    assert client.get('/api/v1/scores/not-a-uuid').status_code == 422
    assert decision(client, low, score).status_code == 404
