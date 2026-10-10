"""Source-linked model output; generated claims never modify lead records."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
from pydantic import ValidationError
from app.modules.foundation.hashing import snapshot_hash
from app.modules.foundation.storage import ArtifactStorage
from app.modules.nlp.business_analysis_model import BusinessAnalysis, ModelDiagnostic
from app.modules.evidence.evidence_model import Evidence
from app.modules.processing.jobs_repository import run_for_job
from app.modules.nlp.business_analysis_schema import BusinessOutput
from app.modules.nlp import model_cache_service as model_cache
from app.modules.nlp.nlp_service import PROMPT_FILE, prompt_identity
from app.modules.processing.workflow_service import StageResult, StageFailure
from app.modules.nlp import ollama_client


def validate_output(raw, chunks, manual):
    data = BusinessOutput.model_validate_json(raw).model_dump()
    warnings = ['MODEL_INTERPRETATION_REQUIRES_REVIEW']
    if manual.get('industry'):
        data['industry'] = {'value': manual['industry'], 'source_id': 'manual:industry', 'quote': manual['industry']}
    if manual.get('employee_count') is not None:
        data['employee_count'] = {'value': manual['employee_count'], 'source_id': 'manual:employee_count',
                                 'quote': str(manual['employee_count'])}
    output = BusinessOutput.model_validate(data)
    sources = {'website_text': [item['text'] for item in chunks]}
    sources.update({f'manual:{key}': [str(value)] for key, value in manual.items() if value is not None})
    def supported(item):
        return item.source_id in sources and (item.source_id != 'website_text' or len(item.quote.strip()) >= 3) and any(item.quote in text for text in sources[item.source_id])
    if output.employee_count is not None:
        fact = output.employee_count
        pattern = rf'(?<!\d){fact.value:,}\s+(?:employees|staff|people|team members)\b|(?<!\d){fact.value}\s+(?:employees|staff|people|team members)\b'
        if not supported(fact) or (fact.source_id == 'website_text' and not re.search(pattern, fact.quote, re.I)):
            output.employee_count = None
            warnings.append('UNSUPPORTED_EMPLOYEE_COUNT_REMOVED')
    citations = [*output.summary_sources, *output.products, *output.markets]
    if output.industry:
        citations.append(output.industry)
    if any(not supported(item) for item in citations):
        raise ValueError('SOURCE_REFERENCE_INVALID')
    # Citation membership alone cannot validate a guessed employee statement in
    # free-form summary text. Require the same explicit size phrase in its quote.
    for phrase in re.finditer(r'\b([0-9][0-9,]*)\s+(employees|staff|people|team members)\b', output.summary, re.I):
        count = int(phrase.group(1).replace(',', ''))
        if manual.get('employee_count') is not None:
            if count != manual['employee_count']:
                raise ValueError('MANUAL_FACT_CONFLICT')
        elif not any(phrase.group().casefold() in item.quote.casefold() for item in output.summary_sources):
            raise ValueError('UNSUPPORTED_SUMMARY_SIZE')
    valid_observations = {'summary', *(f'product:{i}' for i in range(len(output.products))),
                          *(f'market:{i}' for i in range(len(output.markets)))}
    if output.industry:
        valid_observations.add('industry')
    if any(reference not in valid_observations for item in output.opportunities for reference in item.observation_ids):
        raise ValueError('OBSERVATION_REFERENCE_INVALID')
    return output.model_dump(mode='json'), warnings


def correction_feedback(error, raw, manual):
    """Controlled feedback only: never put rejected model text into instructions."""
    feedback = {'problem': 'INVALID_JSON_OR_SCHEMA', 'valid_observation_ids': ['summary']}
    if isinstance(error, ollama_client.InvalidModelOutput):
        feedback['problem'] = 'OUTPUT_TRUNCATED' if error.reason == 'truncated' else 'INVALID_JSON_OR_SCHEMA'
    elif isinstance(error, ValidationError):
        feedback['fields'] = [
            {'field': '.'.join(str(part)[:32] for part in item['loc'])[:64], 'type': item['type'][:32]}
            for item in error.errors(include_input=False, include_url=False)[:3]
        ]
    elif str(error) in ('SOURCE_REFERENCE_INVALID', 'OBSERVATION_REFERENCE_INVALID',
                         'MANUAL_FACT_CONFLICT', 'UNSUPPORTED_SUMMARY_SIZE'):
        feedback['problem'] = str(error)
    try:
        previous = BusinessOutput.model_validate_json(raw)
        feedback['valid_observation_ids'] += [f'product:{i}' for i in range(min(2, len(previous.products)))]
        feedback['valid_observation_ids'] += [f'market:{i}' for i in range(min(2, len(previous.markets)))]
        if previous.industry or manual.get('industry'):
            feedback['valid_observation_ids'].append('industry')
    except ValidationError:
        pass
    return feedback


def build_prompt(snapshot, chunks, *, repair=False, repair_reason=None, feedback=None):
    manual = {key: snapshot['lead'].get(key) for key in ('industry', 'employee_count', 'country')}
    description = snapshot['lead'].get('description')
    manual['description'] = description.encode('utf-8')[:500].decode('utf-8', errors='ignore') if description else None
    data = {'source_id': 'website_text', 'source_chunks': [item['text'] for item in chunks], 'manual': manual,
            'services_context': snapshot.get('services_context', [])}
    prompt = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    if repair:
        prompt += '\nPrevious output failed validation. Correct the JSON schema and exact source excerpts; omit unsupported claims. Return all required keys.'
        if repair_reason == 'truncated':
            prompt += '\nThe previous answer was cut off. Use a shorter summary and empty optional lists so the JSON can finish.'
        if feedback:
            prompt += '\nValidation feedback: ' + json.dumps(feedback, separators=(',', ':'))
            prompt += '\nUse only listed IDs and retain their entries. Omit unsupported opportunities. Copy allowed quotes exactly.'
    return PROMPT_FILE.read_text(encoding='utf-8'), prompt, manual


def generation_schema(chunks, *, observation_ids=None):
    """Keep generation concise and restrict quotes to real, unchanged source excerpts."""
    schema = copy.deepcopy(BusinessOutput.model_json_schema())
    quotes = list(dict.fromkeys(item['text'][:160] for item in chunks if len(item['text'].strip()) >= 3))
    if not quotes: raise StageFailure('TEXT_UNAVAILABLE')
    schema['properties']['summary']['maxLength'] = 240
    for field, maximum in [('summary_sources', 2), ('products', 2), ('markets', 2), ('opportunities', 1)]:
        schema['properties'][field]['maxItems'] = maximum
    for definition in ('Citation', 'CitedValue', 'EmployeeFact'):
        properties = schema['$defs'][definition]['properties']
        properties['source_id']['enum'] = ['website_text']
        properties['quote']['enum'] = quotes
        properties['quote']['maxLength'] = 160
    opportunity = schema['$defs']['Opportunity']['properties']
    opportunity['description']['maxLength'] = 180
    opportunity['observation_ids']['maxItems'] = 2
    opportunity['observation_ids']['items']['enum'] = observation_ids if observation_ids is not None else ['summary', 'industry', 'product:0', 'product:1', 'market:0', 'market:1']
    return schema


def fit_prompt(snapshot, chunks):
    parameters = snapshot['models']['generation']['parameters']
    selected = copy.deepcopy(chunks)
    while selected:
        system, prompt, manual = build_prompt(snapshot, selected, repair=True)
        # Reserve space for bounded field/type feedback and repair instructions.
        upper_bound = len((system + prompt).encode('utf-8')) + 768 + 256 + parameters['num_predict']
        if upper_bound <= parameters['num_ctx']:
            return selected, upper_bound, manual
        last = selected[-1]
        if len(last['text']) <= 100:
            selected.pop()
        else:
            last['text'] = last['text'][:-100]
            last['end'] = last['start'] + len(last['text'])
    raise StageFailure('CONTEXT_LIMIT')


def analyze(context, snapshot, outputs):
    context.checkpoint()
    prepared = outputs.get('preprocess_text', {})
    if not prepared.get('available'):
        return StageResult(state='warning', output={'available': False, 'reason': 'TEXT_UNAVAILABLE'}, warnings=['TEXT_UNAVAILABLE'])
    with context.worker.database.sessions() as session:
        evidence = session.get(Evidence, prepared['evidence_id'])
        if evidence is None or not evidence.usable:
            return StageResult(state='warning', output={'available': False, 'reason': 'TEXT_UNUSABLE'}, warnings=['TEXT_UNUSABLE'])
        evidence_revision = evidence.revision
    generation = snapshot['models'].get('generation')
    if not generation or generation.get('status') != 'available':
        raise StageFailure('MODEL_UNAVAILABLE')
    if snapshot['prompt_version'] != prompt_identity():
        raise StageFailure('PROMPT_CHANGED')
    chunks, token_bound, manual = fit_prompt(snapshot, prepared['chunks'])
    cache_key = snapshot_hash({'schema': snapshot['prompt_version'], 'model': generation, 'manual': manual,
                              'lead_id': snapshot['lead_id'], 'input_revision': snapshot['lead_input_revision'],
                              'services': snapshot.get('services_context'), 'chunks': chunks,
                              'evidence_sha256': outputs['acquire_text']['sha256'], 'evidence_revision': evidence_revision})
    with context.worker.database.sessions() as session:
        cached = model_cache.lookup(session, cache_key)
        cache_payload = copy.deepcopy(cached.cache_payload) if cached else None
        cached_id = cached.id if cached else None
    warnings = []
    stats = {}
    if cache_payload is not None:
        validated, warnings = validate_output(json.dumps(cache_payload), chunks, manual)
    else:
        current = ollama_client.model_info(context.worker.settings)
        context.checkpoint()
        if current['status'] != 'available':
            raise StageFailure('MODEL_UNAVAILABLE')
        if current['digest'] != generation['digest']:
            raise StageFailure('MODEL_CHANGED')
        raw = ''
        repair_reason = None
        feedback = None
        for call in range(2 if context.attempt == 1 else 1):
            context.checkpoint()
            system, prompt, _ = build_prompt(snapshot, chunks, repair=call == 1,
                                           repair_reason=repair_reason, feedback=feedback)
            payload = {'model': generation['name'], 'system': system, 'prompt': prompt, 'stream': False,
                       'format': generation_schema(chunks, observation_ids=feedback['valid_observation_ids'] if feedback else None),
                       'options': generation['parameters'], 'keep_alive': '5m'}
            try:
                raw, stats = ollama_client.generate(context, payload)
                validated, warnings = validate_output(raw, chunks, manual)
                if call:
                    warnings.append('MODEL_OUTPUT_REPAIRED')
                break
            except (ValidationError, ValueError, ollama_client.InvalidModelOutput) as error:
                if isinstance(error, ollama_client.InvalidModelOutput):
                    raw, stats, repair_reason = error.raw, error.stats, error.reason
                feedback = correction_feedback(error, raw, manual)
                if call == 0 and context.attempt == 1:
                    continue
                storage = ArtifactStorage(context.worker.settings.data_dir)
                # Only a controlled diagnostic reference enters the internal error record.
                key = storage.write(raw.encode('utf-8')[:32768], category='diagnostics', suffix='.txt', max_bytes=32768)
                with context.worker.database.transaction(immediate=True) as session:
                    session.add(ModelDiagnostic(lead_id=snapshot['lead_id'], artifact_key=key,
                        expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace('+00:00', 'Z')))
                raise StageFailure('MODEL_OUTPUT_INVALID') from None
            except StageFailure as error:
                # The repair already consumed the second call. Do not let a
                # transport retry silently introduce a third generation call.
                if call and error.retryable:
                    raise StageFailure(error.code, retryable=False) from None
                raise
        if ollama_client.model_info(context.worker.settings).get('digest') != generation['digest']:
            raise StageFailure('MODEL_CHANGED')
    context.checkpoint()
    with context.worker.database.sessions() as session:
        current_evidence = session.get(Evidence, prepared['evidence_id'])
        if not current_evidence.usable or current_evidence.revision != evidence_revision:
            raise StageFailure('EVIDENCE_CHANGED')
    if chunks != prepared['chunks']:
        warnings.append('CONTEXT_TRIMMED')
    if snapshot.get('services_context_truncated'):
        warnings.append('SERVICE_CONTEXT_TRIMMED')
    provenance = {'model': generation, 'prompt': snapshot['prompt_version'], 'input_hash': cache_key,
                  'cache_hit': cached_id is not None, 'cache_origin_analysis_id': cached_id,
                  'evidence_id': prepared['evidence_id'], 'evidence_revision': evidence_revision,
                  'selected_chunks': chunks, 'utf8_byte_token_upper_bound': token_bound, 'runtime_metrics': stats,
                  'sources': {'website_text': prepared['evidence_id']}, 'manual_values_are_user_provided': True,
                  'interpretation_requires_review': True}
    return StageResult(output={'available': True, 'analysis': validated, 'provenance': provenance},
                       usable=True, warnings=list(dict.fromkeys(warnings)))


def persist_analysis(session, job, name, result):
    if name != 'business_analysis' or not result.output.get('available'):
        return
    run = run_for_job(session, job.id)
    analysis_id = str(uuid5(NAMESPACE_URL, f'leadvision:{run.id}:business'))
    if session.get(BusinessAnalysis, analysis_id):
        return
    payload = copy.deepcopy(result.output['analysis'])
    session.add(BusinessAnalysis(id=analysis_id, run_id=run.id, input_hash=result.output['provenance']['input_hash'],
                                result=payload, cache_payload=payload, provenance=result.output['provenance']))
