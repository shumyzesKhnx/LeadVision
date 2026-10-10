"""Idempotent submission, immutable snapshots and read-only polling."""
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Header
from sqlalchemy import select

from app.modules.foundation.errors import AppError
from app.modules.foundation.hashing import snapshot_hash
from app.modules.foundation.clock import utc_now
from app.modules.processing import jobs_repository as repository
from app.modules.icp import icp_repository
from app.modules.processing.job_model import Job, JobStage
from app.modules.processing.analysis_run_model import AnalysisRun
from app.modules.foundation.maintenance_model import WorkerState
from app.modules.processing.job_schema import AnalysisJobCreate, JobRetry, JobReceipt, JobResponse, StageResponse, StageError, JobResult, JobProgress
from app.modules.processing.analysis_run_schema import AnalysisRunResponse
from app.modules.foundation.common_schema import DependencyHealth
from app.modules.processing.activity_service import record_activity
from app.modules.agency.agency_service import require_workspace
from app.modules.campaigns.campaign_service import require_campaign
from app.modules.leads.leads_service import require_lead
from app.modules.processing.workflow_service import STAGES, TERMINAL, FINISHED_STAGES, public_error
from app.modules.processing.worker_lock import lock_is_held


def idempotency_key(value: Annotated[str | None, Header(alias='Idempotency-Key', description='A unique request label, for example arbisoft-analysis-1.')] = None):
    if value is None:
        raise AppError('IDEMPOTENCY_REQUIRED', 'Provide an Idempotency-Key for this request.', 428)
    if not 1 <= len(value) <= 128 or not value.strip() or any(not 32 <= ord(char) <= 126 for char in value):
        raise AppError('INVALID_IDEMPOTENCY_KEY', 'Use 1–128 printable ASCII characters.', 422)
    return value


def worker_readiness(session, settings) -> DependencyHealth:
    state = session.get(WorkerState, 1)
    healthy = False
    if state and state.owner_token and state.heartbeat:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(state.heartbeat.replace('Z', '+00:00'))).total_seconds()
            healthy = 0 <= age <= 15 and lock_is_held(settings.data_dir)
        except (ValueError, OSError):
            healthy = False
    if healthy and not state.worker_paused:
        return DependencyHealth(status='available', message='The worker supports live/saved evidence and local analysis through scoring.')
    return DependencyHealth(status='unavailable', message='Research is paused for maintenance.' if healthy else 'Research is temporarily unavailable. Please try again shortly.')


def require_worker(session, settings):
    if worker_readiness(session, settings).status != 'available':
        raise AppError('WORKER_UNAVAILABLE', 'Research is temporarily unavailable. Please try again shortly.', 503)


def require_job(session, job_id):
    agency = require_workspace(session)
    job = repository.get_job(session, job_id, agency.id)
    if job is None:
        raise AppError('JOB_NOT_FOUND', 'Job not found.', 404)
    return job


def receipt(session, job):
    return JobReceipt(job_id=job.id, status=job.status, poll_url=f'/api/v1/jobs/{job.id}',
                      run_id=repository.run_for_job(session, job.id).id if job.kind == 'analysis' else None)


def preflight_mode(body, session=None, lead_id=None, retry_of=None):
    if body.mode != 'live':
        if not body.upload_token:
            raise AppError('SAVED_EVIDENCE_REQUIRED', 'Upload saved evidence before requesting this mode.', 422)
        from app.modules.evidence.evidence_service import require_upload
        return require_upload(session, lead_id, body, retry_of)
    if body.upload_token is not None:
        raise AppError('INVALID_UPLOAD_TOKEN', 'Live mode does not accept an upload token.', 422)


def snapshot_inputs(session, lead, campaign, body, settings):
    profile = icp_repository.get_icp(session, campaign.icp_id, campaign.agency_id)
    version = icp_repository.current_version(session, profile)
    from app.modules.nlp.business_analysis_model import RuntimeModel
    from app.modules.agency.service_model import Service
    from app.modules.nlp.nlp_service import prompt_identity
    from app.modules.computer_vision.vision_config import vision_identity
    runtime = session.get(RuntimeModel, 1)
    from app.modules.semantics.embedding_model import EmbeddingRuntime
    embedding = session.get(EmbeddingRuntime, 1)
    services = list(session.scalars(select(Service).where(Service.agency_id == campaign.agency_id, Service.active.is_(True))
                                    .order_by(Service.id).limit(11)))
    return {
        'snapshot_version': 1, 'lead_id': lead.id, 'campaign_id': campaign.id,
        'icp_id': profile.id, 'icp_version_id': version.id, 'lead_input_revision': lead.analytical_input_revision,
        'lead': {key: getattr(lead, key) for key in ('company_name', 'website', 'normalized_url', 'industry', 'country',
                                                   'employee_count', 'description')},
        'config': version.config, 'config_hash': version.content_hash,
        'semantic_input_hash': version.semantic_input_hash, 'score_rule_version': version.score_rule_version,
        'request': body.model_dump(mode='json', exclude={'upload_token'}),
        'models': {'generation': {'name': runtime.name if runtime else 'unconfigured',
                   'digest': runtime.digest if runtime else None, 'status': runtime.status if runtime else 'unavailable',
                   'parameters': {'num_ctx': settings.nlp_context_tokens, 'num_predict': settings.nlp_output_tokens,
                                   'temperature': 0, 'seed': 42}},
                   'embedding': {'status': embedding.status, 'identity': embedding.identity} if embedding else {'status': 'unavailable', 'identity': {}}},
        'prompt_version': prompt_identity(), 'vision': vision_identity(), 'stages': list(STAGES),
        'services_context': [{'id': item.id, 'revision': item.revision, 'name': item.name[:80],
                              'description': (item.description or '')[:80]} for item in services[:10]],
        'services_context_truncated': len(services) > 10 or any(len(item.name) > 80 or len(item.description or '') > 80 for item in services),
    }


def submit(session, settings, lead_id, body: AnalysisJobCreate, key, *, retry_of=None):
    lead = require_lead(session, lead_id)
    agency = require_workspace(session)
    scope = f'analysis:{lead.id}'
    canonical = {'request': body.model_dump(mode='json'), 'retry_of_id': retry_of}
    request_hash = snapshot_hash(canonical)
    existing = repository.replay(session, agency.id, scope, key)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AppError('IDEMPOTENCY_CONFLICT', 'This key was already used with a different request.')
        return receipt(session, existing)
    # Replay precedes current-input checks, worker readiness and one-time token attachment.
    campaign = require_campaign(session, lead.campaign_id, for_work=True)
    upload = preflight_mode(body, session, lead.id, retry_of)
    active = repository.active_job(session, lead.id)
    if active is not None:
        from app.modules.foundation.common_schema import ErrorDetail
        raise AppError('ANALYSIS_ACTIVE', 'This lead already has queued or running analysis.', 409,
                       [ErrorDetail(reason=active.id)])
    require_worker(session, settings)
    snapshot = snapshot_inputs(session, lead, campaign, body, settings)
    if upload is not None:
        snapshot.update(saved_upload_id=upload.id, saved_manifest=upload.manifest, saved_imported_at=upload.imported_at)
        if retry_of:
            from app.modules.evidence.evidence_model import Evidence
            previous_run = repository.run_for_job(session, retry_of)
            previous = session.scalars(select(Evidence).where(Evidence.run_id == previous_run.id, Evidence.saved_upload_id == upload.id))
            snapshot['saved_reviews'] = {item.kind: {'evidence_id': item.id, 'revision': item.revision,
                                                    'usable': item.usable, 'reason': item.review_reason} for item in previous}
    job = Job(agency_id=agency.id, lead_id=lead.id, request_hash=request_hash,
              request_body=body.model_dump(mode='json'), input_snapshot=snapshot,
              idempotency_key=key, scope=scope, retry_of_id=retry_of)
    session.add(job)
    session.flush()
    if upload is not None:
        from app.modules.evidence.evidence_service import attach_upload
        attach_upload(upload, job.id)
    run = AnalysisRun(job_id=job.id, lead_id=lead.id, icp_version_id=snapshot['icp_version_id'],
                      lead_input_revision=lead.analytical_input_revision, evidence_mode=body.mode,
                      input_snapshot=snapshot, fingerprint=snapshot_hash(snapshot))
    session.add(run)
    for ordinal, name in enumerate(STAGES):
        session.add(JobStage(job_id=job.id, name=name, ordinal=ordinal, input_hash=run.fingerprint,
                             required=name not in {'validate_inputs', 'finalize'}))
    session.flush()
    record_activity(session, action='analysis.queued', origin='api', agency_id=agency.id,
                    campaign_id=campaign.id, lead_id=lead.id, event_key=f'job:{job.id}:queued',
                    new_value={'job_id': job.id, 'run_id': run.id, 'retry_of_id': retry_of})
    return receipt(session, job)


def job_response(session, job):
    from app.modules.outreach.outreach_model import OutreachDraft
    draft_id = session.scalar(select(OutreachDraft.id).where(OutreachDraft.job_id == job.id)) if job.kind == 'outreach' else None
    stages = repository.stages(session, job.id)
    errors = [StageError(**stage.error) for stage in stages if stage.error]
    if job.error and not any(error.code == job.error['code'] and error.stage == job.error.get('stage') for error in errors):
        errors.append(StageError(**job.error))
    return JobResponse(id=job.id, lead_id=job.lead_id, kind=job.kind, status=job.status,
                       current_stage=job.current_stage, queued_at=job.queued_at, started_at=job.started_at,
                       finished_at=job.finished_at, cancel_requested=job.cancel_requested, retry_of_id=job.retry_of_id,
                       progress=JobProgress(finished_stages=sum(stage.state in FINISHED_STAGES for stage in stages), total_stages=len(stages)),
                       warnings=[warning for stage in stages for warning in stage.warnings], errors=errors,
                       stages=[StageResponse(**{key: getattr(stage, key) for key in StageResponse.model_fields}) for stage in stages],
                       result=JobResult(run_id=repository.run_for_job(session, job.id).id if job.kind == 'analysis' else None, draft_id=draft_id),
                       retryable=job.status in TERMINAL)


def cancel(session, job):
    if job.status in TERMINAL:
        return job_response(session, job)
    job.cancel_requested = True
    if job.status == 'queued':
        job.status = 'cancelled'
        job.finished_at = utc_now()
        job.error = public_error('JOB_CANCELLED')
        for stage in repository.stages(session, job.id):
            stage.state = 'skipped'
            stage.finished_at = job.finished_at
    campaign_id = require_lead(session, job.lead_id).campaign_id if job.kind == 'analysis' else None
    record_activity(session, action=f'{job.kind}.cancel_requested', origin='api', agency_id=job.agency_id,
                    campaign_id=campaign_id, lead_id=job.lead_id, event_key=f'job:{job.id}:cancel',
                    new_value={'job_id': job.id})
    session.flush()
    return job_response(session, job)


def retry(session, settings, job, body: JobRetry, key):
    if job.kind == 'outreach':
        from app.modules.outreach.outreach_schema import OutreachCreate
        from app.modules.outreach.outreach_service import submit as submit_outreach
        if body.upload_token is not None or job.status not in TERMINAL:
            raise AppError('JOB_NOT_RETRYABLE', 'Wait for draft preparation to finish; saved-evidence tokens do not apply.', 409)
        outreach_receipt = submit_outreach(session, settings, job.lead_id, OutreachCreate.model_validate(job.request_body), key, retry_of=job.id)
        return JobReceipt(job_id=outreach_receipt.job_id, status=outreach_receipt.status, poll_url=outreach_receipt.poll_url, run_id=None)
    if job.kind == 'knowledge_index':
        from app.modules.knowledge.knowledge_service import submit_index
        from app.modules.semantics.embedding_model import EmbeddingRuntime
        if body.upload_token is not None:
            raise AppError('INVALID_UPLOAD_TOKEN', 'Knowledge indexing does not accept saved-evidence tokens.', 422)
        if job.status not in TERMINAL:
            raise AppError('JOB_NOT_RETRYABLE', 'Wait for indexing to finish.', 409)
        runtime = session.get(EmbeddingRuntime, 1)
        indexed = submit_index(session, settings, job.input_snapshot['document_id'], job.input_snapshot['version_id'], key,
                               runtime.identity if runtime and runtime.status == 'available' else {}, retry_of=job.id)
        return JobReceipt(job_id=indexed.job_id,status=indexed.status,poll_url=indexed.poll_url,run_id=None)
    request = dict(job.request_body)
    if body.upload_token is not None:
        request['upload_token'] = body.upload_token
    candidate = AnalysisJobCreate.model_validate(request)
    canonical = snapshot_hash({'request': candidate.model_dump(mode='json'), 'retry_of_id': job.id})
    prior = repository.replay(session, job.agency_id, job.scope, key)
    if prior is not None:
        if prior.request_hash != canonical:
            raise AppError('IDEMPOTENCY_CONFLICT', 'Retries need a new key; this key belongs to a different request.')
        return receipt(session, prior)
    if job.status not in {'failed', 'partial', 'cancelled', 'completed'}:
        raise AppError('JOB_NOT_RETRYABLE', 'Wait for the job to finish before requesting a new run.')
    return submit(session, settings, job.lead_id, candidate, key, retry_of=job.id)


def stale_reasons(session, run):
    lead = require_lead(session, run.lead_id)
    campaign = require_campaign(session, lead.campaign_id)
    reasons = []
    profile = icp_repository.get_icp(session, campaign.icp_id, campaign.agency_id)
    if lead.analytical_input_revision != run.lead_input_revision:
        reasons.append('LEAD_INPUT_CHANGED')
    if campaign.archived:
        reasons.append('CAMPAIGN_ARCHIVED')
    if campaign.icp_id != run.input_snapshot['icp_id']:
        reasons.append('CAMPAIGN_ICP_CHANGED')
    if profile.archived:
        reasons.append('ICP_ARCHIVED')
    if profile.current_version_id != run.icp_version_id:
        reasons.append('ICP_VERSION_CHANGED')
    from app.modules.evidence.evidence_model import Evidence
    if session.scalar(select(Evidence.id).where(Evidence.run_id == run.id, Evidence.revision > 1).limit(1)):
        reasons.append('EVIDENCE_REVIEW_CHANGED')
    for review in run.input_snapshot.get('saved_reviews', {}).values():
        source = session.get(Evidence, review['evidence_id'])
        if source is None or source.revision != review['revision']:
            if 'EVIDENCE_REVIEW_CHANGED' not in reasons:
                reasons.append('EVIDENCE_REVIEW_CHANGED')
    from app.modules.nlp.business_analysis_model import RuntimeModel, BusinessAnalysis
    from app.modules.nlp.nlp_service import prompt_identity
    runtime = session.get(RuntimeModel, 1)
    pinned = run.input_snapshot.get('models', {}).get('generation')
    if pinned and pinned.get('digest') and runtime and runtime.status == 'available' and pinned['digest'] != runtime.digest:
        reasons.append('GENERATION_MODEL_CHANGED')
    if run.input_snapshot.get('prompt_version') and run.input_snapshot['prompt_version'] != prompt_identity():
        reasons.append('PROMPT_CHANGED')
    if 'services_context' in run.input_snapshot:
        from app.modules.agency.service_model import Service
        current_services = list(session.scalars(select(Service).where(Service.agency_id == campaign.agency_id, Service.active.is_(True))
                                               .order_by(Service.id).limit(10)))
        if [(item.id, item.revision) for item in current_services] != [(item['id'], item['revision']) for item in run.input_snapshot['services_context']]:
            reasons.append('SERVICES_CHANGED')
    analysis = session.scalar(select(BusinessAnalysis).where(BusinessAnalysis.run_id == run.id))
    if analysis:
        evidence = session.get(Evidence, analysis.provenance['evidence_id'])
        if evidence.revision != analysis.provenance['evidence_revision'] and 'EVIDENCE_REVIEW_CHANGED' not in reasons:
            reasons.append('EVIDENCE_REVIEW_CHANGED')
    from app.modules.computer_vision.vision_config import vision_identity
    if run.input_snapshot.get('vision') and run.input_snapshot['vision'] != vision_identity():
        reasons.append('VISION_CONFIG_CHANGED')
    from app.modules.semantics.embedding_model import EmbeddingRuntime
    from app.modules.semantics.embedding_config import encoder_config
    embedding = session.get(EmbeddingRuntime, 1)
    pinned_embedding = run.input_snapshot.get('models', {}).get('embedding')
    if pinned_embedding and pinned_embedding.get('status') == 'available':
        if embedding and embedding.status == 'available' and embedding.identity != pinned_embedding['identity']:
            reasons.append('EMBEDDING_MODEL_CHANGED')
        elif pinned_embedding['identity']['config'] != encoder_config():
            reasons.append('EMBEDDING_CONFIG_CHANGED')
    from app.modules.semantics.semantic_result_model import SemanticResult
    semantic = session.scalar(select(SemanticResult).where(SemanticResult.run_id == run.id))
    source = semantic.provenance.get('company_source', {}) if semantic else {}
    if source.get('evidence_id'):
        evidence = session.get(Evidence, source['evidence_id'])
        if (evidence is None or evidence.revision != source['evidence_revision']) and 'EVIDENCE_REVIEW_CHANGED' not in reasons:
            reasons.append('EVIDENCE_REVIEW_CHANGED')
    from app.modules.scoring.scoring_service import RULE_VERSION
    if run.input_snapshot['score_rule_version'] != RULE_VERSION: reasons.append('SCORING_RULE_CHANGED')
    return reasons


def run_response(session, run):
    reasons = stale_reasons(session, run)
    job = require_job(session, run.job_id)
    import copy
    snapshot = copy.deepcopy(run.input_snapshot)
    manifest = snapshot.get('saved_manifest', {})
    for kind in ('text', 'image'):
        for key in ('artifact_key', 'thumbnail_key'):
            if kind in manifest:
                manifest[kind].pop(key, None)
    from app.modules.nlp.business_analysis_model import BusinessAnalysis
    analysis = session.scalar(select(BusinessAnalysis).where(BusinessAnalysis.run_id == run.id))
    from app.modules.computer_vision.visual_analysis_model import VisualAnalysis
    visual = session.scalar(select(VisualAnalysis).where(VisualAnalysis.run_id == run.id))
    from app.modules.semantics.semantic_result_model import SemanticResult
    semantic = session.scalar(select(SemanticResult).where(SemanticResult.run_id == run.id))
    from app.modules.scoring.score_model import ScoreRun
    from app.modules.scoring.scoring_service import response as score_response
    score = session.scalar(select(ScoreRun).where(ScoreRun.run_id == run.id))
    return AnalysisRunResponse(**{key: getattr(run, key) for key in ('id', 'lead_id', 'job_id', 'icp_version_id',
                               'lead_input_revision', 'evidence_mode', 'fingerprint', 'created_at')}, input_snapshot=snapshot,
                               is_current=not reasons, stale_reasons=reasons, job=job_response(session, job),
                               business_analysis={'id': analysis.id, 'result': analysis.result, 'provenance': analysis.provenance,
                                                  'created_at': analysis.created_at} if analysis else None,
                               visual_analysis={'id': visual.id, 'result': visual.result, 'provenance': visual.provenance,
                                                'created_at': visual.created_at} if visual else None,
                               semantic_result={'id': semantic.id, 'result': semantic.result, 'provenance': semantic.provenance,
                                                'created_at': semantic.created_at} if semantic else None,
                               score_result=score_response(session, score).model_dump() if score else None)
