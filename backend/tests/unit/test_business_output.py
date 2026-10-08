import json
import pytest
from pydantic import ValidationError
from app.services.business_analysis import validate_output
from app.services.nlp import select_text

TEXT = 'CloudBooks provides accounting software to small businesses.'


def valid_output():
    return {'summary': TEXT, 'summary_sources': [{'source_id': 'website_text', 'quote': TEXT}],
            'industry': None, 'products': [{'value': 'accounting software', 'source_id': 'website_text', 'quote': TEXT}],
            'markets': [], 'employee_count': None, 'opportunities': []}


def test_supported_output_does_not_guess_employees():
    result, warnings = validate_output(json.dumps(valid_output()), [{'text': TEXT}], {})
    assert result['employee_count'] is None and warnings == ['MODEL_INTERPRETATION_REQUIRES_REVIEW']


@pytest.mark.parametrize('change', ['source', 'quote', 'extra', 'length', 'opportunity', 'hypothesis'])
def test_invalid_source_schema_and_opportunities_rejected(change):
    data = valid_output()
    if change == 'source': data['summary_sources'][0]['source_id'] = 'missing'
    if change == 'quote': data['summary_sources'][0]['quote'] = 'Unsupported quote'
    if change == 'extra': data['email'] = 'invented@example.com'
    if change == 'length': data['summary'] = 'x' * 1001
    if change == 'opportunity': data['opportunities'] = [{'description': 'Possible website improvement', 'observation_ids': ['unknown'], 'hypothesis': True}]
    if change == 'hypothesis': data['opportunities'] = [{'description': 'Confirmed need', 'observation_ids': ['summary'], 'hypothesis': False}]
    with pytest.raises((ValueError, ValidationError)):
        validate_output(json.dumps(data), [{'text': TEXT}], {})


def test_employee_claim_needs_explicit_matching_count_and_manual_wins():
    data = valid_output(); data['employee_count'] = {'value': 100, 'source_id': 'website_text', 'quote': TEXT}
    result, warnings = validate_output(json.dumps(data), [{'text': TEXT}], {})
    assert result['employee_count'] is None and 'UNSUPPORTED_EMPLOYEE_COUNT_REMOVED' in warnings
    text = TEXT + ' The company has 20 employees.'
    data['employee_count'] = {'value': 20, 'source_id': 'website_text', 'quote': '20 employees'}
    assert validate_output(json.dumps(data), [{'text': text}], {})[0]['employee_count']['value'] == 20
    result, _ = validate_output(json.dumps(data), [{'text': text}], {'employee_count': 12, 'industry': 'IT'})
    assert result['employee_count'] == {'value': 12, 'source_id': 'manual:employee_count', 'quote': '12'}
    assert result['industry']['value'] == 'IT'


def test_preprocessing_keeps_offsets_and_unicode_bounds():
    original = '  Alpha software  \nAlpha   software\n\nPakistan\n' + '\u0627' * 100
    chunks, decisions = select_text(original, 50)
    assert any(item['action'] == 'duplicate_line_removed' for item in decisions)
    assert any(item['action'] == 'context_trimmed' for item in decisions)
    assert sum(len(item['text'].encode()) for item in chunks) <= 50
    assert all(original[item['start']:item['end']] == item['text'] for item in chunks)


@pytest.mark.parametrize('manual', [{}, {'employee_count': 12}])
def test_summary_cannot_hide_invented_or_conflicting_employee_count(manual):
    data = valid_output()
    data['summary'] = 'CloudBooks has 100 employees.'
    with pytest.raises(ValueError):
        validate_output(json.dumps(data), [{'text': TEXT}], manual)
