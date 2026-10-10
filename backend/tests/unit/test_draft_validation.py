import pytest
from app.modules.outreach.draft_grounding import check_text, restore_missing_excerpts
from app.modules.outreach.draft_template import service_introduction

SOURCES = [{'source_id': 'service', 'kind': 'service', 'text': 'We offer connected security systems.'}]


def text():
    return {'subject': 'Connected security systems', 'body': 'Hello,\nWe offer connected security systems. Would a conversation be useful?',
            'claims': [{'text': 'We offer connected security systems.', 'source_id': 'service', 'quote': 'We offer connected security systems.'}]}


@pytest.mark.parametrize('change', ['source', 'quote', 'number', 'guarantee', 'past_client', 'missing_claim'])
def test_unsupported_draft_claims_are_marked(change):
    data = text()
    if change == 'source': data['claims'][0]['source_id'] = 'unknown'
    if change == 'quote': data['claims'][0]['quote'] = 'Unsupported'
    if change == 'number': data['body'] += ' We improved security by 80%.'
    if change == 'guarantee': data['body'] += ' We guarantee success.'
    if change == 'past_client': data['body'] += ' We previously helped a bank.'
    if change == 'missing_claim': data['claims'] = []
    assert check_text(data, SOURCES)[1]


def test_valid_citation_is_not_called_factual_verification():
    validated, issues = check_text(text(), SOURCES)
    assert issues == [] and 'verified' not in validated


def test_numbers_require_exact_tokens_not_substrings():
    data = text(); data['body'] += ' We have 5 clients.'
    assert check_text(data, [dict(SOURCES[0], text=SOURCES[0]['text']+' 150 projects.')])[1]


def test_fallback_uses_service_quote_without_case_study_claims():
    values, issues = service_introduction({'agency_name': 'Example Agency'}, SOURCES)
    assert issues == [] and 80 <= len(values['body'].split()) <= 150
    assert values['claims'][0]['quote'] == SOURCES[0]['text']
    assert 'past client' not in values['body'].lower()


def test_omitted_real_excerpt_can_be_included_but_fabricated_quote_cannot():
    data = text(); data['body'] = 'Hello, would a conversation about your requirements be useful?'
    restored, changed = restore_missing_excerpts(data, SOURCES)
    assert changed and not check_text(restored, SOURCES)[1]
    assert 'For context:\nWe offer connected security systems.' in restored['body']
    data['claims'][0]['quote'] = data['claims'][0]['text'] = 'We served a bank with 80 employees.'
    restored, changed = restore_missing_excerpts(data, SOURCES)
    assert not changed and check_text(restored, SOURCES)[1]
