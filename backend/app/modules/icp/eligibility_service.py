"""Only explicit entered/reviewed facts can enforce exclusions."""
from app.modules.icp.criteria_service import exclusion_reasons


def evaluate_exclusions(config, facts, reviewed):
    reasons = exclusion_reasons(config['exclusions'], facts, reviewed)
    fields = {'excluded_industry': 'industry', 'excluded_country': 'country', 'excluded_employee_range': 'employee_count'}
    return [{'code': reason, 'field': fields[reason], 'fact': facts[fields[reason]],
             'source': 'user_provided', 'rule': config['exclusions']} for reason in reasons]
