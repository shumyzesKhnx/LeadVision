"""Compare description and target text; structured eligibility remains Phase 11."""
from uuid import uuid5, NAMESPACE_URL
from app.modules.semantics.semantic_result_schema import SemanticValue
from app.modules.processing.workflow_service import StageResult, StageFailure
from app.modules.semantics.embeddings_service import vector_for, cosine
from app.modules.foundation.hashing import snapshot_hash
from app.modules.evidence.evidence_model import Evidence
from app.modules.semantics.semantic_result_model import SemanticResult
from app.modules.processing.job_model import Job
from app.modules.processing.jobs_repository import run_for_job
from app.modules.semantics.embedding_model_client import get_encoder, model_info


def unavailable(reason):
    return StageResult(state='warning', output={'semantic_result': SemanticValue(available=False, reason=reason).model_dump(),
        'provenance': {}}, warnings=[reason])


def choose_company(snapshot, outputs):
    if (snapshot['lead'].get('description') or '').strip():
        return snapshot['lead']['description'], {'source': 'manual_description', 'user_provided': True}
    business = outputs.get('business_analysis', {})
    extracted = outputs.get('acquire_text', {})
    if business.get('available') and business.get('analysis', {}).get('summary', '').strip():
        return business['analysis']['summary'], {'source': 'generated_summary',
            'evidence_id': business['provenance']['evidence_id'], 'evidence_revision': business['provenance']['evidence_revision'],
            'interpretation_requires_review': True}
    if extracted.get('available'):
        return extracted['text'], {'source': 'bounded_website_text',
            'evidence_id': extracted['evidence_id'], 'upstream_truncated': extracted.get('truncated', False)}
    return '', {'source': 'missing'}


def target_text(config):
    target = config['target_text'].strip()
    if not target: return ''
    parts = [target]
    if config.get('desired_needs'): parts.append('Desired needs: ' + '; '.join(config['desired_needs']))
    if (config.get('preferences_text') or '').strip(): parts.append('Preferences: ' + config['preferences_text'].strip())
    return '\n'.join(parts)


def analyze(context, snapshot, outputs):
    context.checkpoint()
    text, source = choose_company(snapshot, outputs)
    target = target_text(snapshot['config'])
    if not text.strip() or not target: return unavailable('EMPTY_TEXT')
    evidence_id = source.get('evidence_id')
    if evidence_id:
        with context.worker.database.sessions() as session:
            evidence = session.get(Evidence, evidence_id)
            if evidence is None or not evidence.usable: return unavailable('TEXT_UNUSABLE')
            if source.get('evidence_revision', evidence.revision) != evidence.revision: return unavailable('EVIDENCE_CHANGED')
            source['evidence_revision'] = evidence.revision
    pinned = snapshot['models'].get('embedding')
    if not pinned or pinned['status'] != 'available': return unavailable('EMBEDDING_UNAVAILABLE')
    if model_info(context.worker.settings) != pinned: return unavailable('EMBEDDING_MODEL_CHANGED')
    try:
        encoder = get_encoder(context.worker, pinned['identity'])
        with context.worker.database.sessions() as session:
            agency_id = session.get(Job, context.job_id).agency_id
        company_id, company, company_selection, company_cached = vector_for(context, encoder, agency_id, 'company', text)
        icp_id, icp, icp_selection, icp_cached = vector_for(context, encoder, agency_id, 'icp', target)
    except StageFailure as error:
        if error.code in {'EMPTY_TEXT', 'ZERO_VECTOR', 'NONFINITE_VECTOR', 'VECTOR_DIMENSION_MISMATCH', 'MODEL_SPACE_MISMATCH'}:
            return unavailable(error.code)
        raise
    context.checkpoint()
    if model_info(context.worker.settings) != pinned: return unavailable('EMBEDDING_MODEL_CHANGED')
    space = snapshot_hash(pinned['identity'])
    raw, value = cosine(company, icp, space, space)
    provenance = {'company_source': source, 'icp_version_id': snapshot['icp_version_id'],
        'icp_input_fields': ['target_text', 'desired_needs', 'preferences_text'],
        'model': pinned['identity'], 'space_hash': space, 'company_embedding_id': company_id, 'icp_embedding_id': icp_id,
        'company': {key: val for key, val in company_selection.items() if key != 'input_ids'},
        'icp': {key: val for key, val in icp_selection.items() if key != 'input_ids'},
        'company_cache_hit': company_cached, 'icp_cache_hit': icp_cached}
    warnings = ['EMBEDDING_TEXT_TRIMMED'] if company_selection['truncated'] or icp_selection['truncated'] else []
    return StageResult(output={'semantic_result': SemanticValue(available=True, raw_cosine=raw,
        normalized_similarity=value).model_dump(), 'provenance': provenance}, usable=True, warnings=warnings)


def persist_semantic(session, job, name, result):
    if name != 'semantic_match' or 'semantic_result' not in result.output: return
    run = run_for_job(session, job.id)
    provenance = result.output['provenance']
    if result.output['semantic_result']['available']:
        source = provenance['company_source']
        if source.get('evidence_id'):
            evidence = session.get(Evidence, source['evidence_id'])
            if evidence is None or not evidence.usable or evidence.revision != source['evidence_revision']:
                raise StageFailure('EVIDENCE_CHANGED')
    session.add(SemanticResult(id=str(uuid5(NAMESPACE_URL, f'leadvision:{run.id}:semantic')), run_id=run.id,
        company_embedding_id=provenance.get('company_embedding_id'), icp_embedding_id=provenance.get('icp_embedding_id'),
        result=result.output['semantic_result'], provenance=provenance))
