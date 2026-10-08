"""Production handlers are deliberately minimal until evidence/AI modules exist."""
from app.services.workflow import StageResult


def validate_inputs(context, snapshot, previous_outputs):
    context.checkpoint()
    return StageResult(output={'validated': True, 'snapshot_version': snapshot['snapshot_version']})


def production_handlers():
    from app.services.evidence import saved_stage
    from app.services.nlp import preprocess
    from app.services.business_analysis import analyze
    # Modules 07–11 register real handlers here; tests inject their own fake mapping.
    return {'validate_inputs': validate_inputs,
            'acquire_text': lambda context, snapshot, outputs: saved_stage(context, snapshot, 'text'),
            'acquire_image': lambda context, snapshot, outputs: saved_stage(context, snapshot, 'image'),
            'preprocess_text': preprocess, 'business_analysis': analyze}
