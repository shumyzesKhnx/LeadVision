"""Weighted fit v1: unknown is missing; coverage and exclusions are independent."""
import math
import copy
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from app.modules.foundation.errors import AppError
from app.modules.scoring.score_model import ScoreRun, ScoreComponent
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.evidence.evidence_model import Evidence
from app.modules.processing.jobs_repository import run_for_job
from app.modules.scoring import scores_repository as repository
from app.modules.icp.criteria_service import eligible_components, target_countries, industry_label
from app.modules.icp.eligibility_service import evaluate_exclusions
from app.modules.processing.workflow_service import StageResult, StageFailure
from app.modules.scoring.score_schema import ScoreResponse

RULE_VERSION = 'weighted-fit-v1'
NAMES = ('industry', 'geography', 'size', 'semantic', 'visual')


def band(score, thresholds):
    if score is None: return None
    return 'High' if score >= thresholds['high'] else ('Medium' if score >= thresholds['medium'] else 'Low')


def calculate(config, facts, semantic=None, reviewed=None):
    from app.modules.icp.icp_schema import AnalyticalConfig
    try:
        config = AnalyticalConfig.model_validate(config).model_dump()
        if config['weights']['visual'] != 0 or config['visual_calibration_id'] is not None:
            raise ValueError('Visual scoring is not calibrated.')
        applicable = eligible_components(config)
        if not applicable: raise ValueError('No applicable positive weights.')
    except (ValueError, AppError):
        raise StageFailure('SCORING_CONFIG_INVALID') from None
    reviewed = set(reviewed or ())
    criteria = config['criteria']; components = []
    for name in NAMES:
        weight = config['weights'][name]; selected = name in applicable
        value = None; source = 'missing'; reason = 'No supported input.'
        if name == 'industry' and 'industry' in reviewed and facts.get('industry'):
            value = 100.0 if industry_label(facts['industry']) in criteria['industries'] else 0.0
            source = 'user_provided'; reason = 'Entered industry matches the target.' if value else 'Entered industry differs from the target.'
        elif name == 'geography' and 'country' in reviewed and facts.get('country'):
            value = 100.0 if facts['country'] in target_countries(criteria) else 0.0
            source = 'user_provided'; reason = 'Entered country is in the target area.' if value else 'Entered country is outside the target area.'
        elif name == 'size' and 'employee_count' in reviewed and type(facts.get('employee_count')) is int and facts['employee_count'] >= 0:
            count = facts['employee_count']
            inside = (criteria['employee_min'] is None or count >= criteria['employee_min']) and (criteria['employee_max'] is None or count <= criteria['employee_max'])
            value = 100.0 if inside else 0.0; source = 'user_provided'
            reason = 'Entered employee count is within inclusive bounds.' if inside else 'Entered employee count is outside the bounds.'
        elif name == 'semantic' and semantic is not None:
            if type(semantic) in (int, float) and math.isfinite(semantic) and 0 <= semantic <= 100:
                value = float(semantic); source = 'semantic_result'; reason = 'Compatible text similarity, scaled to 0-100.'
        elif name == 'visual': reason = 'Visual scoring is disabled until reviewed calibration exists.'
        if not selected: value = None; reason = 'Not applicable or configured weight is zero.'
        available = selected and value is not None
        components.append({'name': name, 'state': 'available' if available else ('missing' if selected else 'not_applicable'),
            'value': value, 'configured_weight': weight, 'eligible_weight': weight if selected else 0.0,
            'available_weight': weight if available else 0.0, 'numerator': weight * value if available else 0.0,
            'normalized_contribution': 0.0, 'source': source if available else 'missing', 'explanation': reason})
    eligible = sum(item['eligible_weight'] for item in components)
    available = sum(item['available_weight'] for item in components)
    numerator = sum(item['numerator'] for item in components)
    total = numerator / available if available else None
    coverage = available / eligible
    for item in components:
        item['normalized_contribution'] = item['numerator'] / available if available else 0.0
    thresholds = config['thresholds']; score_band = band(total, thresholds)
    priority = score_band if total is not None and coverage >= thresholds['minimum_coverage'] else 'Needs review'
    exclusions = evaluate_exclusions(config, facts, reviewed)
    return {'score': total, 'coverage': coverage, 'score_band': score_band, 'priority': priority,
        'ineligible': bool(exclusions), 'exclusion_reasons': exclusions,
        'recommended_for_qualification': priority == 'High' and not exclusions,
        'components': components, 'thresholds': thresholds, 'eligible_weight': eligible,
        'available_weight': available, 'numerator': numerator}


def analyze(context, snapshot, outputs):
    context.checkpoint()
    if snapshot['score_rule_version'] != RULE_VERSION: raise StageFailure('SCORING_RULE_CHANGED')
    facts = {key: snapshot['lead'].get(key) for key in ('industry', 'country', 'employee_count')}
    reviewed = {key for key, value in facts.items() if value is not None}
    semantic_stage = outputs.get('semantic_match', {})
    semantic_result = semantic_stage.get('semantic_result', {})
    semantic = semantic_result.get('normalized_similarity') if semantic_result.get('available') else None
    evidence_revisions = {}
    source = semantic_stage.get('provenance', {}).get('company_source', {})
    if source.get('evidence_id'):
        with context.worker.database.sessions() as session:
            evidence = session.get(Evidence, source['evidence_id'])
            if evidence is None or not evidence.usable or evidence.revision != source['evidence_revision']: semantic = None
            else: evidence_revisions[evidence.id] = evidence.revision
    result = calculate(snapshot['config'], facts, semantic, reviewed)
    provenance = {'rule_version': RULE_VERSION, 'icp_version_id': snapshot['icp_version_id'],
        'config_hash': snapshot['config_hash'], 'lead_input_revision': snapshot['lead_input_revision'],
        'facts': facts, 'reviewed_fields': sorted(reviewed), 'user_provided_is_not_independently_verified': True,
        'semantic_provenance': semantic_stage.get('provenance', {}) if semantic is not None else None,
        'evidence_revisions': evidence_revisions, 'thresholds': snapshot['config']['thresholds']}
    return StageResult(output={'score_result': result, 'provenance': provenance}, usable=result['score'] is not None,
        warnings=['SCORE_INCOMPLETE'] if result['coverage'] < 1 else [])


def persist_score(session, job, name, result):
    if name != 'score' or 'score_result' not in result.output: return
    run = run_for_job(session, job.id); score_id = str(uuid5(NAMESPACE_URL, f'leadvision:{run.id}:score'))
    if session.get(ScoreRun, score_id): return
    payload = copy.deepcopy(result.output['score_result']); provenance = result.output['provenance']
    for evidence_id, revision in provenance['evidence_revisions'].items():
        evidence = session.get(Evidence, evidence_id)
        if evidence is None or not evidence.usable or evidence.revision != revision:
            raise StageFailure('EVIDENCE_CHANGED')
    components = payload.pop('components')
    session.add(ScoreRun(id=score_id, run_id=run.id, lead_id=run.lead_id, result=payload, provenance=provenance)); session.flush()
    for component in components:
        session.add(ScoreComponent(id=str(uuid5(NAMESPACE_URL, f'{score_id}:{component["name"]}')),
                                   score_id=score_id, name=component['name'], result=component))
    from app.modules.processing.activity_service import record_activity
    record_activity(session, action='score.calculated', origin='worker', agency_id=job.agency_id,
                    lead_id=job.lead_id, campaign_id=job.input_snapshot['campaign_id'],
                    event_key=f'score:{score_id}:saved', new_value={'score_id': score_id, 'run_id': run.id})


def require_score(session, score_id):
    row = session.get(ScoreRun, score_id)
    if row is None: raise AppError('SCORE_NOT_FOUND', 'Score not found.', 404)
    from app.modules.leads.leads_service import require_lead
    require_lead(session, row.lead_id)
    return row


def response(session, row, *, include_overrides=True):
    from app.modules.processing.jobs_service import stale_reasons
    run = session.get(AnalysisRun, row.run_id); reasons = stale_reasons(session, run)
    if row.provenance['rule_version'] != RULE_VERSION and 'SCORING_RULE_CHANGED' not in reasons: reasons.append('SCORING_RULE_CHANGED')
    newest = repository.latest(session, row.lead_id)
    if newest and newest.id != row.id: reasons.append('SUPERSEDED_SCORE')
    values = copy.deepcopy(row.result)
    if reasons: values['priority'] = 'Needs review'; values['recommended_for_qualification'] = False
    components = list(session.scalars(select(ScoreComponent).where(ScoreComponent.score_id == row.id)))
    result = ScoreResponse(id=row.id, run_id=row.run_id, lead_id=row.lead_id, created_at=row.created_at,
        **values, provenance=row.provenance, components=sorted([item.result for item in components], key=lambda c: NAMES.index(c['name'])),
        is_current=not reasons, stale_reasons=reasons)
    if include_overrides:
        from app.modules.scoring.overrides_service import attach
        attach(session, row, result)
    return result
