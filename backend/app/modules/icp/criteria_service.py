"""Explicit matching vocabulary; free text never becomes an exclusion rule."""

from app.modules.foundation.errors import AppError
from app.modules.foundation.common_schema import ErrorDetail

# ISO 3166-1 alpha-2 codes. GB is the canonical code for the United Kingdom.
COUNTRY_CODES = frozenset('''AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ
BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ
DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY
HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP
KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY
MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ
NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY
QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ
TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ
VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'''.split())

REGIONS = {
    'uk': ['GB'],
    'north_america': ['CA', 'MX', 'US'],
    'gcc': ['AE', 'BH', 'KW', 'OM', 'QA', 'SA'],
    'eu': ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR',
           'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL',
           'PT', 'RO', 'SE', 'SI', 'SK'],
}
INDUSTRY_SYNONYMS = {'saas': 'software', 'software as a service': 'software',
                     'ecommerce': 'e-commerce', 'e commerce': 'e-commerce'}


def industry_label(value: str) -> str:
    label = ' '.join(value.casefold().split())
    return INDUSTRY_SYNONYMS.get(label, label)


def country_code(value: str) -> str:
    code = value.strip().upper()
    if code == 'UK':
        code = 'GB'
    if code not in COUNTRY_CODES:
        raise ValueError('Use an ISO two-letter country code, such as GB or PK.')
    return code


def region_key(value: str) -> str:
    key = value.strip().casefold().replace(' ', '_')
    if key not in REGIONS:
        raise AppError('UNKNOWN_REGION', 'Choose a supported region from ICP options.', 422,
                       [ErrorDetail(field='criteria.regions', reason='Use uk, eu, north_america or gcc.')])
    return key


def target_countries(criteria: dict) -> list[str]:
    countries = set(criteria['countries'])
    for region in criteria['regions']:
        countries.update(REGIONS[region])
    return sorted(countries)


def eligible_components(config: dict) -> list[str]:
    criteria = config['criteria']
    selected = {
        'industry': bool(criteria['industries']),
        'geography': bool(target_countries(criteria)),
        'size': criteria['employee_min'] is not None or criteria['employee_max'] is not None,
        'semantic': bool(config['target_text'].strip()),
        'visual': bool(config.get('visual_calibration_id')),
    }
    return [key for key, applicable in selected.items() if applicable and config['weights'][key] > 0]


def exclusion_reasons(exclusions: dict, facts: dict, verified_fields: set[str]) -> list[str]:
    """Only known/reviewed facts can enforce rules; model guesses are not enough."""
    reasons = []
    if 'industry' in verified_fields and isinstance(facts.get('industry'), str):
        if industry_label(facts['industry']) in exclusions['industries']:
            reasons.append('excluded_industry')
    if 'country' in verified_fields and isinstance(facts.get('country'), str):
        try:
            code = country_code(facts['country'])
        except ValueError:
            code = None
        if code in exclusions['countries']:
            reasons.append('excluded_country')
    count = facts.get('employee_count')
    if 'employee_count' in verified_fields and type(count) is int and count >= 0:
        minimum, maximum = exclusions['employee_min'], exclusions['employee_max']
        if (minimum is not None or maximum is not None) and (
            (minimum is None or count >= minimum) and (maximum is None or count <= maximum)
        ):
            reasons.append('excluded_employee_range')
    return reasons
