"""Conservative source selection with original offsets and a UTF-8 byte token bound."""
from pathlib import Path
import re
from app.core.hashing import content_hash
from app.services.workflow import StageResult

PROMPT_FILE = Path(__file__).resolve().parents[1] / 'prompts/business_analysis_v1.txt'
PROMPT_VERSION = 'business_analysis_v1'
SCHEMA_VERSION = 'business_output_v1'


def prompt_identity():
    return {'version': PROMPT_VERSION, 'sha256': content_hash(PROMPT_FILE.read_bytes()), 'schema_version': SCHEMA_VERSION}


def select_text(text, budget_bytes):
    seen, chunks, decisions = set(), [], []
    used = 0
    for match in re.finditer(r'[^\r\n]+', text):
        original = match.group()
        left = len(original) - len(original.lstrip())
        right = len(original.rstrip())
        line = original[left:right]
        if not line:
            continue
        normalized = ' '.join(line.split()).casefold()
        if normalized in seen:
            decisions.append({'action': 'duplicate_line_removed', 'start': match.start(), 'end': match.end()})
            continue
        seen.add(normalized)
        remaining = max(0, budget_bytes - used)
        selected = line.encode('utf-8')[:remaining].decode('utf-8', errors='ignore')
        if selected:
            start = match.start() + left
            chunks.append({'text': selected, 'start': start, 'end': start + len(selected)})
            used += len(selected.encode('utf-8'))
        if len(selected) != len(line):
            decisions.append({'action': 'context_trimmed', 'start': match.start() + left + len(selected), 'end': len(text)})
            break
    return chunks, decisions


def preprocess(context, snapshot, outputs):
    context.checkpoint()
    source = outputs.get('acquire_text', {})
    if not source.get('available'):
        return StageResult(state='warning', output={'available': False}, warnings=['TEXT_UNAVAILABLE'])
    chunks, decisions = select_text(source['text'], context.worker.settings.nlp_evidence_bytes)
    return StageResult(output={'available': bool(chunks), 'source_id': 'website_text',
        'evidence_id': source['evidence_id'], 'chunks': chunks, 'decisions': decisions,
        'utf8_byte_token_upper_bound': sum(len(item['text'].encode('utf-8')) for item in chunks),
        'upstream_truncated': source.get('truncated', False)}, warnings=['CONTEXT_TRIMMED'] if any(
            item['action'] == 'context_trimmed' for item in decisions) else [])
