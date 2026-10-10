import pytest
from pydantic import ValidationError

from app.modules.foundation.errors import AppError
from app.modules.icp.criteria_service import COUNTRY_CODES, exclusion_reasons
from app.modules.icp.icp_service import validate_config


def config(**changes):
    return validate_config({'target_text': 'Software companies needing a better website.', **changes})


def test_defaults_eligibility_and_country_canonicalization():
    value = config(criteria={'industries': [' SaaS ', 'software'], 'countries': ['uk', 'GB'],
                             'employee_min': 0, 'employee_max': 100})
    assert value['criteria']['industries'] == ['software']
    assert value['criteria']['countries'] == ['GB']
    assert value['weights'] == dict(industry=25, geography=20, size=15, semantic=40, visual=0)
    assert len(COUNTRY_CODES) == 249


@pytest.mark.parametrize('weights', [{'industry': -1}, {'semantic': float('nan')},
                                    {'semantic': float('inf')}, {'size': True}, {'size': '20'}])
def test_invalid_weights_are_rejected(weights):
    with pytest.raises(ValidationError):
        config(weights=weights)


@pytest.mark.parametrize('criteria', [{'employee_min': -1}, {'employee_min': 20.5},
                                     {'employee_max': True}, {'countries': ['ZZ']}, {'industries': [' ']}])
def test_invalid_criteria_are_rejected(criteria):
    with pytest.raises(ValidationError):
        config(criteria=criteria)


def test_eligible_total_and_semantic_requirements():
    with pytest.raises(AppError, match='INVALID_WEIGHTS'):
        validate_config({'target_text': '', 'weights': {'semantic': 40}})
    with pytest.raises(AppError, match='INVALID_WEIGHTS'):
        validate_config({'target_text': '', 'weights': {'semantic': 0}})
    # Unselected geography/size/industry do not make a usable denominator.
    with pytest.raises(AppError, match='INVALID_WEIGHTS'):
        config(weights={'industry': 0, 'geography': 0, 'size': 0, 'semantic': 0})
    assert validate_config({'target_text': '', 'criteria': {'employee_min': 0},
                            'weights': {'semantic': 0}})['criteria']['employee_min'] == 0


def test_exclusions_only_match_verified_facts_and_free_text_stays_guidance():
    value = config(exclusions={'industries': ['SaaS'], 'countries': ['UK'], 'employee_min': 10, 'employee_max': 20},
                   preferences_text='Exclude every company in Pakistan.')
    exclusions = value['exclusions']
    facts = {'industry': 'software', 'country': 'GB', 'employee_count': 15}
    assert exclusion_reasons(exclusions, facts, set()) == []
    assert exclusion_reasons(exclusions, facts, {'industry', 'country', 'employee_count'}) == [
        'excluded_industry', 'excluded_country', 'excluded_employee_range']
    assert exclusion_reasons(exclusions, {'country': 'PK'}, {'country'}) == []
    assert exclusion_reasons(exclusions, {'employee_count': None}, {'employee_count'}) == []
    assert exclusions['countries'] == ['GB']
