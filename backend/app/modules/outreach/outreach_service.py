"""Queue drafts with pinned context; retain separate generated draft series."""
import copy
from sqlalchemy import select
from app.modules.foundation.errors import AppError
from app.modules.foundation.hashing import snapshot_hash
from app.modules.agency.agency_service import require_workspace
from app.modules.agency.agency_model import Agency
from app.modules.agency.service_model import Service
from app.modules.leads.leads_service import require_lead
from app.modules.campaigns.campaign_service import require_campaign
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.nlp.business_analysis_model import BusinessAnalysis, RuntimeModel
from app.modules.processing.job_model import Job, JobStage
from app.modules.processing.jobs_service import stale_reasons, require_worker
from app.modules.processing import jobs_repository
from app.modules.processing.activity_service import record_activity
from app.modules.outreach.draft_grounding import prompt_identity
from app.modules.outreach.outreach_model import OutreachDraft
from app.modules.outreach import outreach_repository as repository
from app.modules.outreach.outreach_schema import OutreachReceipt


def context_snapshot(session, lead_id, body):
    lead = require_lead(session, lead_id)
    campaign = require_campaign(session, lead.campaign_id)
    if campaign.archived:
        raise AppError('CONTEXT_STALE', 'Choose an active campaign.', 409)
    service = session.scalar(select(Service).where(Service.id == str(body.service_id), Service.agency_id == campaign.agency_id, Service.active.is_(True)))
    if service is None:
        raise AppError('NO_ACTIVE_SERVICE', 'Choose an active agency service.', 409)
    run = session.get(AnalysisRun, str(body.analysis_run_id)) if body.analysis_run_id else session.scalar(select(AnalysisRun).where(AnalysisRun.lead_id == lead.id).order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc()))
    if not run or run.lead_id != lead.id:
        raise AppError('CONTEXT_MISSING', 'Research this company before preparing outreach.', 409)
    job = session.get(Job, run.job_id)
    if stale_reasons(session, run) or job.status not in ('completed', 'partial'):
        raise AppError('CONTEXT_STALE', 'Run current company research before preparing outreach.', 409)
    analysis = session.scalar(select(BusinessAnalysis).where(BusinessAnalysis.run_id == run.id))
    sources = [{'source_id': 'service', 'title': service.name, 'text': f'{service.name}: {service.description or ""}',
                'kind': 'service', 'service_id': service.id, 'revision': service.revision}]
    if lead.description:
        sources.append({'source_id': 'company:manual', 'title': 'Company description (user entered)',
                        'text': lead.description[:600], 'kind': 'manual'})
    if analysis:
        quotes = list(dict.fromkeys(item['quote'] for item in analysis.result['summary_sources']))
        sources.append({'source_id': 'company:website', 'title': 'Researched company evidence',
                        'text': '\n'.join(quotes)[:1000], 'kind': 'company',
                        'evidence_id': analysis.provenance['evidence_id'], 'evidence_revision': analysis.provenance['evidence_revision']})
    elif not body.acknowledge_missing_analysis:
        raise AppError('CONTEXT_MISSING', 'Business analysis is missing. Explicitly acknowledge using limited company context.', 409)
    if len(sources) == 1:
        raise AppError('CONTEXT_MISSING', 'Add a factual company description or finish its business analysis.', 409)
    agency = session.get(Agency, campaign.agency_id)
    return {'snapshot_version': 1, 'lead_id': lead.id, 'campaign_id': campaign.id, 'agency_id': agency.id,
            'agency_name': agency.name, 'agency_revision': agency.revision, 'run_id': run.id,
            'lead_input_revision': lead.analytical_input_revision, 'service_id': service.id,
            'service_revision': service.revision, 'company_name': lead.company_name,
            'sources': sources, 'limited_context': analysis is None, 'prompt': prompt_identity()}


def grounding_stale(session, snapshot):
    from app.modules.knowledge.knowledge_model import KnowledgeDocument
    reasons = []
    lead = require_lead(session, snapshot['lead_id'])
    service = session.get(Service, snapshot['service_id'])
    agency = session.get(Agency, snapshot['agency_id'])
    run = session.get(AnalysisRun, snapshot['run_id'])
    if lead.analytical_input_revision != snapshot['lead_input_revision']:
        reasons.append('Company details changed')
    if not service or not service.active or service.revision != snapshot['service_revision']:
        reasons.append('Selected service changed')
    if agency.revision != snapshot['agency_revision']:
        reasons.append('Agency details changed')
    if not run or stale_reasons(session, run):
        reasons.append('Company research is outdated')
    if snapshot['prompt'] != prompt_identity():
        reasons.append('Draft instructions changed')
    for source in snapshot['sources']:
        if source['kind'] == 'knowledge':
            document = session.get(KnowledgeDocument, source['document_id'])
            if not document or not document.active or not document.approved or document.current_version_id != source['version_id'] or document.revision != source['document_revision']:
                reasons.append('Agency knowledge changed')
    return list(dict.fromkeys(reasons))


def receipt(job):
    return OutreachReceipt(job_id=job.id, status=job.status, poll_url=f'/api/v1/jobs/{job.id}')


def submit(session, settings, lead_id, body, key, *, retry_of=None):
    lead = require_lead(session, lead_id)
    agency = require_workspace(session)
    scope = f'outreach:{lead.id}'
    request = body.model_dump(mode='json')
    fingerprint = snapshot_hash({'request': request, 'retry_of_id': retry_of})
    prior = jobs_repository.replay(session, agency.id, scope, key)
    if prior:
        if prior.request_hash != fingerprint:
            raise AppError('IDEMPOTENCY_CONFLICT', 'Use a new key for a different outreach request.', 409)
        return receipt(prior)
    require_worker(session, settings)
    if session.scalar(select(Job.id).where(Job.lead_id == lead.id, Job.kind == 'outreach', Job.status.in_(['queued', 'running']))):
        raise AppError('OUTREACH_ACTIVE', 'A draft is already being prepared for this company.', 409)
    snapshot = context_snapshot(session, lead_id, body)
    model = session.get(RuntimeModel, 1)
    if not model or model.status != 'available':
        raise AppError('MODEL_UNAVAILABLE', 'Draft preparation is temporarily unavailable.', 503)
    snapshot['models'] = {'generation': {'name': model.name, 'digest': model.digest,
        'parameters': {'num_ctx': settings.outreach_context_tokens, 'num_predict': settings.outreach_output_tokens, 'temperature': 0, 'seed': 42}}}
    snapshot['request'] = request
    job = Job(agency_id=agency.id, lead_id=lead.id, kind='outreach', scope=scope, request_body=request,
              input_snapshot=snapshot, request_hash=fingerprint, idempotency_key=key, retry_of_id=retry_of)
    session.add(job); session.flush()
    for ordinal, name in enumerate(('retrieve_outreach', 'prepare_outreach', 'finalize')):
        session.add(JobStage(job_id=job.id, name=name, ordinal=ordinal, input_hash=snapshot_hash(snapshot), required=name != 'finalize'))
    record_activity(session, action='outreach.queued', origin='api', agency_id=agency.id, lead_id=lead.id,
                    campaign_id=lead.campaign_id, event_key=f'job:{job.id}:queued', new_value={'job_id': job.id})
    return receipt(job)


def require_draft(session, draft_id):
    agency = require_workspace(session)
    draft = session.scalar(select(OutreachDraft).where(OutreachDraft.id == str(draft_id), OutreachDraft.agency_id == agency.id))
    if draft is None:
        raise AppError('DRAFT_NOT_FOUND', 'Outreach draft not found.', 404)
    return draft


def response(session, draft):
    history = repository.revisions(session, draft.id)
    def item(row):
        return {key: getattr(row, key) for key in ('id', 'number', 'state', 'subject', 'body', 'claims', 'unresolved_claims', 'reviewer', 'reason', 'created_at')}
    return {'id': draft.id, 'lead_id': draft.lead_id, 'service_id': draft.service_id, 'job_id': draft.job_id,
            'revision': draft.revision, 'created_at': draft.created_at, 'current_revision': item(history[0]),
            'history': [item(row) for row in history], 'sources': repository.sources(session, draft.id),
            'stale_reasons': grounding_stale(session, draft.grounding), 'warnings': draft.warnings,
            'retrieval': draft.retrieval, 'provenance': draft.provenance}
