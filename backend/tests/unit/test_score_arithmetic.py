import copy
import pytest
from app.modules.icp.icp_schema import AnalyticalConfig
from app.modules.scoring.scoring_service import calculate
from app.modules.processing.workflow_service import StageFailure


def config():
    return AnalyticalConfig(target_text='Accounting software', criteria={'industries': ['software'], 'countries': ['GB'],
        'employee_min': 20, 'employee_max': 100}).model_dump()


def test_reference_arithmetic_contributions_and_missing_size():
    result = calculate(config(), {'industry': 'software', 'country': 'GB'}, 80, {'industry', 'country'})
    assert result['numerator'] == 7700 and result['available_weight'] == 85 and result['eligible_weight'] == 100
    assert result['score'] == pytest.approx(90.58823529411765) and result['coverage'] == .85
    assert sum(component['normalized_contribution'] for component in result['components']) == pytest.approx(result['score'])
    assert result['priority'] == 'High' and result['recommended_for_qualification']


def test_only_industry_high_number_low_coverage_and_all_missing():
    result = calculate(config(), {'industry': 'software'}, reviewed={'industry'})
    assert result['score'] == 100 and result['coverage'] == .25
    assert result['score_band'] == 'High' and result['priority'] == 'Needs review'
    assert not result['recommended_for_qualification']
    missing = calculate(config(), {})
    assert missing['score'] is None and missing['coverage'] == 0


def test_known_zero_counts_as_available_and_unselected_size_is_removed():
    cfg = config(); cfg['criteria']['employee_min'] = cfg['criteria']['employee_max'] = None
    result = calculate(cfg, {'industry': 'construction'}, reviewed={'industry'})
    assert result['score'] == 0 and result['coverage'] == pytest.approx(25 / 85)
    assert result['eligible_weight'] == 85
    assert result['components'][-1]['state'] == 'not_applicable'


@pytest.mark.parametrize('value,expected', [(49.999, 'Low'), (50, 'Medium'), (74.999, 'Medium'), (75, 'High')])
def test_exact_band_boundaries(value, expected):
    cfg = AnalyticalConfig(target_text='Software').model_dump()
    result = calculate(cfg, {}, value)
    assert result['score_band'] == expected and result['coverage'] == 1


@pytest.mark.parametrize('coverage,recommended', [(.5999, False), (.6, True)])
def test_exact_coverage_boundary(coverage, recommended):
    cfg = config(); cfg['weights'] = {'industry': coverage * 100, 'geography': (1 - coverage) * 100, 'size': 0, 'semantic': 0, 'visual': 0}
    result = calculate(cfg, {'industry': 'software'}, reviewed={'industry'})
    assert result['recommended_for_qualification'] == recommended


def test_custom_thresholds_and_unreviewed_model_facts():
    cfg = config(); cfg['thresholds'] = {'high': 80, 'medium': 55, 'minimum_coverage': .8}
    result = calculate(cfg, {'industry': 'software', 'country': 'GB', 'employee_count': 30}, 75, set())
    assert result['score'] == 75 and result['score_band'] == 'Medium' and result['coverage'] == .4
    assert result['priority'] == 'Needs review'


@pytest.mark.parametrize('change', [{'weights': {'industry': 0, 'geography': 0, 'size': 0, 'semantic': 0, 'visual': 0}},
    {'weights': {'visual': 1}}, {'thresholds': {'medium': 80, 'high': 70}}])
def test_invalid_config_fails_safely(change):
    cfg = config(); cfg.update(change)
    with pytest.raises(StageFailure, match='SCORING_CONFIG_INVALID'): calculate(cfg, {})


def test_exclusions_do_not_change_arithmetic_and_free_text_is_not_a_rule():
    cfg = config(); cfg['criteria']['countries'] = ['PK']; cfg['exclusions']['countries'] = ['PK']
    result = calculate(cfg, {'industry': 'software', 'country': 'PK', 'employee_count': 30}, 100, {'industry', 'country', 'employee_count'})
    assert result['score'] == 100 and result['ineligible'] and not result['recommended_for_qualification']
    cfg['exclusions']['countries'] = []; cfg['preferences_text'] = 'Do not work with Pakistan'
    result = calculate(cfg, {'country': 'PK'}, 100, {'country'})
    assert not result['ineligible']


def test_employee_exclusion_uses_inclusive_known_range_and_unknown_is_not_excluded():
    cfg = config(); cfg['exclusions']['employee_min'] = 20; cfg['exclusions']['employee_max'] = 100
    for count in (20, 100):
        assert calculate(cfg, {'employee_count': count}, reviewed={'employee_count'})['ineligible']
    assert not calculate(cfg, {}, reviewed=set())['ineligible']
