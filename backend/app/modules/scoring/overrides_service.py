"""Append reviewer decisions beside arithmetic, bound to explicit current inputs."""
from sqlalchemy import select
from app.modules.foundation.hashing import snapshot_hash
from app.modules.foundation.errors import AppError
from app.modules.foundation.revisions import check_revision
from app.modules.scoring.reviewer_override_model import ReviewerOverride
from app.modules.evidence.evidence_model import Evidence
from app.modules.campaigns.campaign_model import Campaign
from app.modules.icp.icp_model import ICP
from app.modules.semantics.embedding_model import EmbeddingRuntime
from app.modules.nlp.business_analysis_model import RuntimeModel
from app.modules.agency.service_model import Service
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.processing.activity_service import record_activity
from app.modules.scoring.scores_repository import latest


def binding(session, lead, row):
    campaign = session.get(Campaign, lead.campaign_id); profile = session.get(ICP, campaign.icp_id)
    generation = session.get(RuntimeModel, 1); embedding = session.get(EmbeddingRuntime, 1)
    services = list(session.scalars(select(Service).where(Service.agency_id == campaign.agency_id, Service.active.is_(True)).order_by(Service.id)))
    reviews = list(session.scalars(select(Evidence).where(Evidence.run_id == row.run_id).order_by(Evidence.id)))
    from app.modules.nlp.nlp_service import prompt_identity
    from app.modules.computer_vision.vision_config import vision_identity
    return {'fingerprint': snapshot_hash({'score_id': row.id, 'lead_revision': lead.analytical_input_revision,
        'icp_version': profile.current_version_id, 'campaign_icp': campaign.icp_id, 'archived': [campaign.archived, profile.archived],
        'reviews': [(item.id, item.revision, item.usable) for item in reviews],
        'services': [(item.id, item.revision) for item in services], 'prompt': prompt_identity(), 'vision': vision_identity(),
        'generation': [generation.status, generation.digest] if generation else None,
        'embedding': [embedding.status, embedding.identity] if embedding else None})}


def attach(session, row, result):
    from app.modules.leads.leads_service import require_lead
    lead = require_lead(session, row.lead_id)
    current_binding = binding(session, lead, row)
    newest = latest(session, lead.id)
    records = list(session.scalars(select(ReviewerOverride).where(ReviewerOverride.score_id == row.id)
                                  .order_by(ReviewerOverride.created_at.desc(), ReviewerOverride.id.desc())))
    seen = set()
    for item in records:
        active = (item.kind not in seen and item.value != 'clear' and newest.id == row.id and item.binding == current_binding
                  and (result.is_current or item.kind == 'qualification'))
        seen.add(item.kind)
        result.overrides.append({'id': item.id, 'kind': item.kind, 'value': item.value, 'reason': item.reason,
                                 'reviewer': item.reviewer, 'created_at': item.created_at, 'active': active})
        if active:
            if item.kind == 'priority': result.reviewer_priority = item.value
            elif item.kind == 'exclusion': result.exclusion_override = True
            elif item.kind == 'qualification': result.qualification_override = True


def create(session, lead_id, body, expected):
    from app.modules.leads.leads_service import require_lead
    from app.modules.scoring.scoring_service import require_score, response
    lead = require_lead(session, lead_id); check_revision(lead.revision, expected)
    row = require_score(session, str(body.score_id))
    if row.lead_id != lead.id: raise AppError('SCORE_NOT_FOUND', 'Score not found.', 404)
    if latest(session, lead.id).id != row.id: raise AppError('OVERRIDE_SCORE_SUPERSEDED', 'Choose the latest score for this lead.')
    score = response(session, row, include_overrides=False)
    if not score.is_current and body.kind != 'qualification':
        raise AppError('OVERRIDE_SCORE_STALE', 'Recompute before overriding priority or exclusions.')
    if body.kind == 'exclusion' and body.value == 'allow' and not score.ineligible:
        raise AppError('INVALID_OVERRIDE', 'This score has no hard exclusion to override.', 422)
    count = len(list(session.scalars(select(ReviewerOverride.id).where(ReviewerOverride.score_id == row.id))))
    if count >= 100: raise AppError('OVERRIDE_LIMIT', 'Create a new analysis before adding more reviewer decisions.')
    item = ReviewerOverride(lead_id=lead.id, score_id=row.id, **body.model_dump(exclude={'score_id'}), binding=binding(session, lead, row))
    session.add(item); session.flush()
    campaign = session.get(Campaign, lead.campaign_id)
    record_activity(session, action='score.override_recorded', origin='api', agency_id=campaign.agency_id,
                    campaign_id=campaign.id, lead_id=lead.id, event_key=f'override:{item.id}',
                    new_value={'override_id': item.id, 'kind': item.kind, 'score_id': row.id})
    return response(session, row)
