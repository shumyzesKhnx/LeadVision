import json
import pytest
from pydantic import ValidationError
from app.modules.nlp.business_analysis_service import validate_output
from app.modules.nlp.nlp_service import select_text
from app.modules.nlp.business_analysis_service import generation_schema, correction_feedback, fit_prompt, build_prompt

TEXT = 'CloudBooks provides accounting software to small businesses.'


def test_real_bank_details_fit_with_correction_space_and_source_text():
    snapshot = {'lead': {'industry': 'banking', 'country': 'US', 'employee_count': None,
                        'description': 'Bank based in Utica, New York, offering personal and business banking, deposit accounts, loans, and online banking.'},
                'services_context': [{'id': '2f75ccb8-94bb-44a5-bedb-f9eebfe175cd', 'revision': 7,
                                      'name': 'Connected security systems',
                                      'description': 'IoT device integration, cloud monitoring, and mobile/web applications for connec'}],
                'models': {'generation': {'parameters': {'num_ctx': 4096, 'num_predict': 768}}}}
    text = 'Bank of Utica offers personal and business banking. ' * 32
    chunks, bound, manual = fit_prompt(snapshot, [{'text': text, 'start': 0, 'end': len(text)}])
    assert chunks and len(chunks[0]['text']) >= 300
    assert bound <= 4096 and manual['industry'] == 'banking'
    feedback = {'problem': 'OBSERVATION_REFERENCE_INVALID', 'valid_observation_ids': ['summary', 'market:0', 'industry']}
    system, prompt, _ = build_prompt(snapshot, chunks, repair=True, feedback=feedback)
    assert len((system + prompt).encode()) + 256 + 768 <= 4096
    assert text[chunks[0]['start']:chunks[0]['end']] == chunks[0]['text']


def valid_output():
    return {'summary': TEXT, 'summary_sources': [{'source_id': 'website_text', 'quote': TEXT}],
            'industry': None, 'products': [{'value': 'accounting software', 'source_id': 'website_text', 'quote': TEXT}],
            'markets': [], 'employee_count': None, 'opportunities': []}


def test_supported_output_does_not_guess_employees():
    result, warnings = validate_output(json.dumps(valid_output()), [{'text': TEXT}], {})
    assert result['employee_count'] is None and warnings == ['MODEL_INTERPRETATION_REQUIRES_REVIEW']


def test_schema_feedback_names_missing_fields_without_rejected_values():
    raw = '{"summary":"PRIVATE_REJECTED_TEXT"}'
    with pytest.raises(ValidationError) as caught:
        validate_output(raw, [{'text': TEXT}], {})
    feedback = correction_feedback(caught.value, raw, {})
    assert feedback['problem'] == 'INVALID_JSON_OR_SCHEMA'
    assert feedback['fields'][0] == {'field': 'summary_sources', 'type': 'missing'}
    assert feedback['valid_observation_ids'] == ['summary']
    assert 'PRIVATE_REJECTED_TEXT' not in json.dumps(feedback)
    assert len(json.dumps(feedback).encode()) < 768


def test_generation_contract_only_offers_real_quotes_and_valid_reference_names():
    chunks = [{'text': 'First source line.'}, {'text': 'Second source line.'}, {'text': 'x' * 200}]
    schema = generation_schema(chunks)
    for name in ('Citation', 'CitedValue', 'EmployeeFact'):
        choices = schema['$defs'][name]['properties']['quote']['enum']
        assert all(any(quote in chunk['text'] for chunk in chunks) for quote in choices)
        assert all(len(quote) <= 160 for quote in choices)
        assert 'First source line. Second source line.' not in choices
    ids = schema['$defs']['Opportunity']['properties']['observation_ids']['items']['enum']
    assert '01' not in ids and 'summary' in ids and 'product:0' in ids
    assert schema['properties']['products']['maxItems'] == 2
    assert schema['properties']['summary']['maxLength'] == 240


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
