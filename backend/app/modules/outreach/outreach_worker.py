import copy
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
from pydantic import ValidationError
from app.modules.foundation.errors import AppError
from app.modules.processing.workflow_service import StageResult, StageFailure
from app.modules.nlp import ollama_client
from app.modules.knowledge.knowledge_schema import RetrievalPreview
from app.modules.knowledge.knowledge_model import KnowledgeDocument, KnowledgeChunk
from app.modules.processing.job_model import Job
from app.modules.knowledge.retrieval_service import preview
from app.modules.outreach.draft_grounding import PROMPT_FILE, prompt_identity, check_text, generation_schema, restore_missing_excerpts
from app.modules.outreach.outreach_service import grounding_stale
from app.modules.outreach.outreach_model import OutreachDraft, OutreachRevision, DraftSource
from app.modules.nlp.business_analysis_model import ModelDiagnostic
from app.modules.foundation.storage import ArtifactStorage
from app.modules.outreach.draft_template import service_introduction


def retrieve(context, snapshot, outputs):
    context.checkpoint()
    with context.worker.database.sessions() as session:
        if grounding_stale(session, snapshot):
            raise StageFailure('INPUT_CHANGED')
    pinned = snapshot['models']['generation']
    if ollama_client.model_info(context.worker.settings).get('digest') != pinned['digest']:
        raise StageFailure('MODEL_CHANGED')
    query = snapshot['company_name'] + '. ' + next((s['text'][:250] for s in snapshot['sources'] if s['kind'] == 'manual'), '')
    query += '. Relevant service: ' + snapshot['sources'][0]['title'][:100]
    try:
        retrieved = preview(context.worker.database, context.worker.settings, RetrievalPreview(query_text=query[:450]))
    except AppError as error:
        raise StageFailure(error.code) from None
    sources = copy.deepcopy(snapshot['sources'])
    with context.worker.database.sessions() as session:
        for item in retrieved.sources:
            document = session.get(KnowledgeDocument, item.document_id)
            chunk = session.get(KnowledgeChunk, item.chunk_id)
            index_job = session.get(Job, chunk.job_id) if chunk else None
            if not document or not document.active or not document.approved or document.current_version_id != item.version_id:
                raise StageFailure('INPUT_CHANGED')
            if not index_job or index_job.status != 'completed' or index_job.input_snapshot['document_revision'] != document.revision:
                raise StageFailure('INPUT_CHANGED')
            sources.append({'source_id': f'knowledge:{item.chunk_id}', 'kind': 'knowledge', 'title': item.title,
                            'text': item.text, 'document_revision': document.revision, **item.model_dump()})
    warnings = ['FACTUAL_REVIEW_REQUIRED']
    if not retrieved.sources:
        warnings.append('NO_RELEVANT_KNOWLEDGE_SERVICE_ONLY')
    if snapshot['limited_context']:
        warnings.append('LIMITED_COMPANY_CONTEXT')
    # Preserve exact prefixes and the full historical retrieval separately.
    for item in sources:
        if len(item['text']) > 700:
            item['text'] = item['text'][:700]
            warnings.append('DRAFT_SOURCE_CONTEXT_TRIMMED')
    return StageResult(output={'sources': sources, 'retrieval': retrieved.model_dump(),
                              'warnings': list(dict.fromkeys(warnings))})


def generate(context, snapshot, outputs):
    context.checkpoint()
    prepared = outputs['retrieve_outreach']
    sources = prepared['sources']
    warnings = list(prepared['warnings'])
    pinned = snapshot['models']['generation']
    parameters = pinned['parameters']
    if ollama_client.model_info(context.worker.settings).get('digest') != pinned['digest']:
        raise StageFailure('MODEL_CHANGED')
    data = {'agency': snapshot['agency_name'], 'company': snapshot['company_name'], 'sources': sources}
    system = PROMPT_FILE.read_text(encoding='utf-8')
    base = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    if len((system + base).encode()) + parameters['num_predict'] + 1024 > parameters['num_ctx']:
        raise StageFailure('CONTEXT_LIMIT')
    feedback = None
    raw = ''
    stats = {}
    method = 'local_model'
    for call in range(2 if context.attempt == 1 else 1):
        context.checkpoint()
        prompt = base
        if feedback:
            prompt += '\nCorrect the output. Validation issues: ' + json.dumps(feedback, separators=(',', ':'))
            prompt += '\nCopy source quotes exactly; remove unsupported claims. Return every required key.'
        payload = {'model': pinned['name'], 'system': system, 'prompt': prompt, 'format': generation_schema(sources),
                   'options': parameters, 'stream': False, 'keep_alive': '5m'}
        try:
            raw, stats = ollama_client.generate(context, payload)
            candidate, excerpts_added = restore_missing_excerpts(json.loads(raw), sources)
            values, issues = check_text(candidate, sources)
            if issues:
                source_map = {item['source_id']: item['text'] for item in sources}
                excerpts = [claim['text'] for claim in values['claims']
                            if claim['text'] == claim['quote'] and claim['quote'] in source_map.get(claim['source_id'], '')
                            and claim['text'] not in values['body']][:2]
                feedback = {'issues': [item[:100] for item in issues[:3]], 'required_body_excerpts': excerpts}
                raise ValueError('Unsupported claims')
            if excerpts_added:
                warnings.append('DRAFT_SOURCE_EXCERPTS_ADDED')
            if call:
                warnings.append('DRAFT_OUTPUT_REPAIRED')
            break
        except (ValidationError, ValueError, ollama_client.InvalidModelOutput) as error:
            if isinstance(error, ollama_client.InvalidModelOutput):
                raw = error.raw
            if not feedback:
                feedback = {'issue': 'Return complete valid JSON with subject, body and source-linked claims.'}
                if isinstance(error, ollama_client.InvalidModelOutput):
                    feedback['issue'] = 'Output was truncated. Shorten the body and claim list.'
            if call == 0 and context.attempt == 1:
                continue
            storage = ArtifactStorage(context.worker.settings.data_dir)
            key = storage.write(raw.encode('utf-8')[:32768], category='diagnostics', suffix='.txt', max_bytes=32768)
            with context.worker.database.transaction(immediate=True) as session:
                session.add(ModelDiagnostic(lead_id=snapshot['lead_id'], artifact_key=key,
                    expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace('+00:00', 'Z')))
            values, issues = service_introduction(snapshot, sources)
            if issues:
                raise StageFailure('DRAFT_OUTPUT_INVALID') from None
            warnings.append('TEMPLATE_FALLBACK_MODEL_OUTPUT_INVALID')
            method = 'service_template'
            break
        except StageFailure as error:
            if call and error.retryable:
                raise StageFailure(error.code, retryable=False) from None
            raise
    context.checkpoint()
    if ollama_client.model_info(context.worker.settings).get('digest') != pinned['digest']:
        raise StageFailure('MODEL_CHANGED')
    grounding = {**copy.deepcopy(snapshot), 'sources': sources}
    with context.worker.database.sessions() as session:
        if grounding_stale(session, grounding):
            raise StageFailure('INPUT_CHANGED')
    if not 80 <= len(values['body'].split()) <= 150:
        warnings.append('DRAFT_LENGTH_REQUIRES_REVIEW')
    return StageResult(usable=True, output={'draft': values, 'sources': sources, 'grounding': grounding,
        'retrieval': prepared['retrieval'], 'provenance': {'prompt': prompt_identity(), 'model': pinned, 'runtime_metrics': stats, 'method': method},
        'warnings': list(dict.fromkeys(warnings))}, warnings=list(dict.fromkeys(warnings)))


def persist(session, job, result):
    output = result.output
    if grounding_stale(session, output['grounding']):
        raise StageFailure('INPUT_CHANGED')
    draft_id = str(uuid5(NAMESPACE_URL, f'leadvision:{job.id}:outreach'))
    if session.get(OutreachDraft, draft_id):
        return
    session.add(OutreachDraft(id=draft_id, agency_id=job.agency_id, lead_id=job.lead_id, job_id=job.id,
        service_id=job.input_snapshot['service_id'], grounding=output['grounding'], retrieval=output['retrieval'],
        provenance=output['provenance'], warnings=output['warnings']))
    session.flush()
    session.add(OutreachRevision(draft_id=draft_id, number=1, state='Generated', **output['draft'], unresolved_claims=[]))
    for source in output['sources']:
        session.add(DraftSource(draft_id=draft_id, source_id=source['source_id'], snapshot=source))
