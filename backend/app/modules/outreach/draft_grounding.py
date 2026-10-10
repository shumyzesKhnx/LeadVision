"""Validate references without claiming to prove natural-language entailment."""
import json
import re
from pathlib import Path
from app.modules.foundation.hashing import content_hash
from app.modules.outreach.outreach_schema import DraftText

PROMPT_FILE = Path(__file__).with_name('outreach_v1.txt')


def prompt_identity():
    return {'version': 'outreach_v1', 'schema_version': 'outreach_exact_excerpt_v2', 'sha256': content_hash(PROMPT_FILE.read_bytes())}


def restore_missing_excerpts(data, sources):
    """Include omitted exact source excerpts; never fabricate a citation or change its meaning."""
    values = DraftText.model_validate(data).model_dump()
    source_map = {item['source_id']: item['text'] for item in sources}
    missing = list(dict.fromkeys(claim['text'] for claim in values['claims']
        if claim['text'] == claim['quote'] and claim['quote'] in source_map.get(claim['source_id'], '')
        and claim['text'] not in values['subject'] + '\n' + values['body']))
    if missing:
        candidate = values['body'] + '\n\nFor context:\n' + '\n'.join(missing)
        if len(candidate) <= 2000:
            values['body'] = candidate
            return values, True
    return values, False


def check_text(text, sources):
    data = DraftText.model_validate(text).model_dump()
    source_map = {item['source_id']: item for item in sources}
    unresolved = []
    combined = data['subject'] + '\n' + data['body']
    for index, claim in enumerate(data['claims']):
        source = source_map.get(claim['source_id'])
        if claim['text'] not in combined or not source or claim['quote'] not in source['text']:
            unresolved.append(f'Claim {index + 1} needs a valid source excerpt.')
    supported = '\n'.join(item['text'] for item in sources)
    supported_numbers = set(re.findall(r'\b\d[\d,.%]*', supported))
    for number in re.findall(r'\b\d[\d,.%]*', combined):
        if number not in supported_numbers:
            unresolved.append(f'Unsupported number: {number}')
    if re.search(r'\b(guarantee|guaranteed|your (?:outdated|insecure|bad) website)\b', combined, re.I):
        unresolved.append('Remove guarantees or unsupported website-quality judgments.')
    if not any(item['kind'] == 'knowledge' for item in sources) and re.search(
            r'\b(case stud(?:y|ies)|past clients?|worked with|built for|delivered for|previously helped)\b', combined, re.I):
        unresolved.append('No retrieved knowledge supports a past-client or case-study claim.')
    # Every factual assertion still needs human review; citations only establish membership.
    if not data['claims']:
        unresolved.append('Identify the factual claims and their supporting sources.')
    return data, list(dict.fromkeys(unresolved))


def generation_schema(sources):
    schema = DraftText.model_json_schema()
    schema['required'] = ['subject', 'body', 'claims']
    schema['properties']['subject']['maxLength'] = 100
    schema['properties']['claims']['maxItems'] = 3
    claim = schema['$defs']['Claim']['properties']
    claim['source_id']['enum'] = [item['source_id'] for item in sources]
    choices = []
    for source in sources:
        for sentence in re.split(r'(?<=[.!?])\s+|\n+', source['text']):
            excerpt = sentence.strip()[:240]
            if len(excerpt) >= 3:
                choices.append(excerpt)
    choices = list(dict.fromkeys(choices))[:32]
    claim['quote']['enum'] = choices
    claim['text']['enum'] = choices
    return schema
