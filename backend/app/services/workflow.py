"""Shared stage order and safe handler contracts for modules 07–11."""
import json
import re
from pydantic import Field, model_validator
from app.schemas.common import StrictModel

STAGES = ('validate_inputs', 'acquire_text', 'acquire_image', 'preprocess_text',
          'business_analysis', 'visual_metrics', 'semantic_match', 'score', 'finalize')
TERMINAL = {'completed', 'partial', 'failed', 'cancelled'}
FINISHED_STAGES = {'succeeded', 'warning', 'failed', 'skipped'}


class StageResult(StrictModel):
    state: str = 'succeeded'
    output: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    usable: bool = False

    @model_validator(mode='after')
    def bounded_output(self):
        if self.state not in {'succeeded', 'warning', 'skipped'}:
            raise ValueError('Invalid handler outcome.')
        if self.state == 'skipped' and self.usable:
            raise ValueError('Skipped stages cannot claim usable output.')
        if any(len(warning) > 200 for warning in self.warnings):
            raise ValueError('Warning exceeds its limit.')
        if len(json.dumps(self.output, ensure_ascii=False, allow_nan=False).encode()) > 131072:
            raise ValueError('Stage output exceeds its limit; store an artifact reference instead.')
        def validate_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if not isinstance(key, str) or key.casefold() in {'password', 'secret', 'api_key', 'authorization', 'credentials'} or key.casefold().endswith('_path'):
                        raise ValueError('Public stage output cannot contain secrets or filesystem paths.')
                    validate_keys(child)
            elif isinstance(value, list):
                for child in value:
                    validate_keys(child)
        validate_keys(self.output)
        return self


class StageFailure(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        if not re.fullmatch('[A-Z][A-Z0-9_]{0,99}', code):
            raise ValueError('Invalid safe stage code.')
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def public_error(code, stage=None, retryable=False):
    messages = {
        'STAGE_NOT_IMPLEMENTED': 'This processing stage is implemented in a later phase.',
        'JOB_INTERRUPTED': 'The worker stopped before the job finished. Retry to create a new run.',
        'INPUT_CHANGED': 'Inputs changed while this job was queued. Request a new analysis.',
        'JOB_TIMEOUT': 'The job exceeded its processing deadline.',
        'STAGE_TIMEOUT': 'The stage exceeded its processing deadline.',
        'JOB_CANCELLED': 'Cancellation was requested; saved outputs remain available.',
        'INVALID_STAGE_OUTPUT': 'The processing stage returned an invalid result.',
        'MODEL_UNAVAILABLE': 'The configured local model is unavailable. Evidence remains saved.',
        'MODEL_TIMEOUT': 'The local model did not finish within its deadline.',
        'MODEL_OUTPUT_INVALID': 'The model output failed validation after its recovery budget.',
        'MODEL_CHANGED': 'The installed model changed after this job was saved. Request a new run.',
        'PROMPT_CHANGED': 'The analysis prompt changed. Request a new run.',
        'CONTEXT_LIMIT': 'The selected inputs exceed the configured model context.',
        'EVIDENCE_CHANGED': 'The text review changed during processing. Request a new run.',
    }
    return {'code': code, 'message': messages.get(code, 'The processing stage could not complete.'),
            'stage': stage, 'retryable': retryable}
