"""Lead creation/corrections, append-only provenance and scoped deletion."""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.foundation.clock import utc_now
from app.modules.foundation.errors import AppError
from app.modules.foundation.revisions import check_revision
from app.modules.foundation.urls import normalize_website
from app.modules.leads import leads_repository as repository
from app.modules.processing.jobs_repository import active_job, latest_job
from app.modules.leads.company_model import Company
from app.modules.leads.lead_model import Lead
from app.modules.foundation.common_schema import ErrorDetail
from app.modules.leads.lead_schema import LeadCreate, LeadPatch, LeadDetail, LeadResponse, LeadFactResponse, LeadActivityResponse, LeadInvalidation
from app.modules.processing.activity_service import record_activity
from app.modules.agency.agency_service import require_workspace
from app.modules.campaigns.campaign_service import require_campaign

FACT_FIELDS = {'company_name', 'website', 'industry', 'country', 'employee_count', 'contact_name', 'contact_email', 'description', 'notes'}
ANALYTICAL_FIELDS = {'company_name', 'website', 'industry', 'country', 'employee_count', 'description'}


def name_key(value: str) -> str:
    return ' '.join(value.casefold().split())


def require_lead(session: Session, lead_id: str) -> Lead:
    agency = require_workspace(session)
    lead = repository.get_lead(session, lead_id, agency.id)
    if lead is None:
        raise AppError('LEAD_NOT_FOUND', 'Lead not found.', 404)
    return lead


def duplicate_error(lead: Lead):
    return AppError('DUPLICATE_DOMAIN', 'This company website is already in the campaign.', 409,
                    [ErrorDetail(field='website', reason=lead.id)])


def lead_response(session: Session, lead: Lead, *, detail: bool = False, changed_fields=None):
    fields = {field: getattr(lead, field) for field in LeadResponse.model_fields if hasattr(lead, field)}
    fields['normalized_domain'] = session.get(Company, lead.company_id).normalized_domain
    job = latest_job(session, lead.id)
    fields['processing_status'] = job.status if job else 'not_started'
    fields['latest_job_id'] = job.id if job else None
    fields['warnings'] = ['POSSIBLE_NAME_DUPLICATE'] if repository.duplicate_name(session, lead) else []
    from app.modules.scoring.scores_repository import latest as latest_score
    from app.modules.scoring.scoring_service import response as score_response
    score_row = latest_score(session, lead.id)
    score = score_response(session, score_row) if score_row else None
    if score:
        fields.update({key: getattr(score, key) for key in ('score', 'coverage', 'score_band', 'priority', 'is_current',
                      'ineligible', 'recommended_for_qualification', 'reviewer_priority')})
        fields['score_id'] = score.id
    if not detail:
        return LeadResponse(**fields)
    activities, total = repository.recent_activities(session, lead.id)
    changed = sorted(changed_fields or [])
    affected = 0
    if ANALYTICAL_FIELDS.intersection(changed):
        from sqlalchemy import select, func
        from app.modules.scoring.score_model import ScoreRun
        from app.modules.processing.analysis_run_model import AnalysisRun
        affected = session.scalar(select(func.count()).select_from(ScoreRun)
            .join(AnalysisRun, AnalysisRun.id == ScoreRun.run_id)
            .where(ScoreRun.lead_id == lead.id,
                   AnalysisRun.lead_input_revision == lead.analytical_input_revision - 1)) or 0
    return LeadDetail(**fields, score_components=score.components if score else [], score_detail=score.model_dump() if score else None,
                      provenance=[LeadFactResponse.model_validate(fact) for fact in repository.latest_facts(session, lead.id)],
                      activities=[LeadActivityResponse.model_validate(event) for event in activities], activities_total=total,
                      invalidation=LeadInvalidation(analytical_inputs_changed=bool(ANALYTICAL_FIELDS.intersection(changed)),
                                                    changed_fields=changed, affected_results=affected))


def create_lead(session: Session, body: LeadCreate, *, origin: str = 'api') -> LeadDetail:
    campaign = require_campaign(session, str(body.campaign_id), for_work=True)
    identity = normalize_website(body.website)
    company = repository.company_for_domain(session, identity.domain)
    duplicate = repository.duplicate_domain(session, campaign.id, company.id)
    if duplicate is not None:
        raise duplicate_error(duplicate)
    values = body.model_dump(mode='json', exclude={'campaign_id'})
    lead = Lead(campaign_id=campaign.id, company_id=company.id, normalized_url=identity.normalized_url,
                name_key=name_key(body.company_name), **values)
    session.add(lead)
    session.flush()
    for field in sorted(FACT_FIELDS):
        if field in body.model_fields_set and getattr(lead, field) is not None:
            repository.append_fact(session, lead.id, field, getattr(lead, field), None)
    record_activity(session, action='lead.imported' if origin == 'import' else 'lead.created', origin=origin,
                    agency_id=campaign.agency_id, campaign_id=campaign.id, lead_id=lead.id,
                    event_key=f'lead:{lead.id}:created', new_value={'revision': 1, 'pipeline_state': 'New'})
    return lead_response(session, lead, detail=True)


def edit_lead(session: Session, lead_id: str, body: LeadPatch, expected: int) -> LeadDetail:
    lead = require_lead(session, lead_id)
    check_revision(lead.revision, expected)
    values = body.model_dump(mode='json', exclude_unset=True, exclude={'correction_reason'})
    changes = {field: value for field, value in values.items() if value != getattr(lead, field)}
    if not changes:
        return lead_response(session, lead, detail=True)
    changed_fields = sorted(changes)
    old_company = lead.company_id
    if 'website' in changes:
        identity = normalize_website(changes['website'])
        company = repository.company_for_domain(session, identity.domain)
        duplicate = repository.duplicate_domain(session, lead.campaign_id, company.id, lead.id)
        if duplicate is not None:
            raise duplicate_error(duplicate)
        changes.update(company_id=company.id, normalized_url=identity.normalized_url)
    if 'company_name' in changes:
        changes['name_key'] = name_key(changes['company_name'])
    input_revision = lead.analytical_input_revision + bool(ANALYTICAL_FIELDS.intersection(changed_fields))
    changes.update(revision=expected + 1, analytical_input_revision=input_revision, updated_at=utc_now())
    if not repository.update_lead(session, lead, expected, changes):
        raise AppError('EDIT_CONFLICT', 'This lead changed. Reload it before saving.')
    for field in changed_fields:
        repository.append_fact(session, lead.id, field, getattr(lead, field), body.correction_reason)
    campaign = require_campaign(session, lead.campaign_id)
    record_activity(session, action='lead.updated', origin='api', agency_id=campaign.agency_id,
                    campaign_id=campaign.id, lead_id=lead.id, old_value={'revision': expected},
                    new_value={'revision': lead.revision, 'fields': changed_fields,
                               'analytical_input_revision': input_revision})
    if lead.company_id != old_company:
        repository.remove_unused_company(session, old_company)
    return lead_response(session, lead, detail=True, changed_fields=changed_fields)


def delete_lead(session: Session, lead_id: str, expected: int, confirmed: bool, storage=None) -> int:
    if not confirmed:
        raise AppError('DELETE_CONFIRMATION_REQUIRED', 'Set confirm=true to delete this lead.', 409)
    lead = require_lead(session, lead_id)
    check_revision(lead.revision, expected)
    campaign = require_campaign(session, lead.campaign_id)
    if active_job(session, lead.id, kind=None) is not None:
        raise AppError('ANALYSIS_ACTIVE', 'Cancel the queued/running job before deleting this lead.')
    cleanup_count = 0
    if storage is not None:
        from app.modules.evidence.evidence_service import queue_lead_artifacts
        cleanup_count = queue_lead_artifacts(session, storage, lead.id)
    record_activity(session, action='lead.deleted', origin='api', agency_id=campaign.agency_id,
                    campaign_id=campaign.id, new_value={'deleted_lead_id': lead.id})
    company_id = lead.company_id
    from app.modules.semantics.embedding_model import Embedding, EmbeddingLead
    from app.modules.semantics.semantic_result_model import SemanticResult
    from sqlalchemy import or_, exists, select
    embedding_ids = list(session.scalars(select(EmbeddingLead.embedding_id).where(EmbeddingLead.lead_id == lead.id)))
    session.execute(delete(Lead).where(Lead.id == lead.id, Lead.revision == expected))
    if embedding_ids:
        session.execute(delete(Embedding).where(Embedding.id.in_(embedding_ids), Embedding.purpose == 'company',
            ~exists(select(EmbeddingLead.embedding_id).where(EmbeddingLead.embedding_id == Embedding.id)),
            ~exists(select(SemanticResult.id).where(or_(SemanticResult.company_embedding_id == Embedding.id,
                                                      SemanticResult.icp_embedding_id == Embedding.id)))))
    repository.remove_unused_company(session, company_id)
    return cleanup_count
