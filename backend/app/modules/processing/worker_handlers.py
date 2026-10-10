"""Implemented processing stages; later modules add semantic matching and scoring."""
from app.modules.processing.workflow_service import StageResult


def validate_inputs(context, snapshot, previous_outputs):
    context.checkpoint()
    return StageResult(output={'validated': True, 'snapshot_version': snapshot['snapshot_version']})


def production_handlers():
    from app.modules.evidence.evidence_service import saved_stage
    from app.modules.evidence.live_evidence_service import collect_text, collect_image
    from app.modules.nlp.nlp_service import preprocess
    from app.modules.nlp.business_analysis_service import analyze
    from app.modules.computer_vision.vision_service import analyze as analyze_image
    from app.modules.semantics.semantic_matching_service import analyze as match_text
    from app.modules.scoring.scoring_service import analyze as score
    from app.modules.knowledge.knowledge_index_service import index_knowledge
    from app.modules.outreach.outreach_worker import generate as prepare_outreach, retrieve as retrieve_outreach
    # Modules 07–11 register real handlers here; tests inject their own fake mapping.
    return {'validate_inputs': validate_inputs,
            'acquire_text': lambda context, snapshot, outputs: collect_text(context, snapshot, outputs) if snapshot['request']['mode'] == 'live' else saved_stage(context, snapshot, 'text'),
            'acquire_image': lambda context, snapshot, outputs: collect_image(context, snapshot, outputs) if snapshot['request']['mode'] == 'live' else saved_stage(context, snapshot, 'image'),
            'preprocess_text': preprocess, 'business_analysis': analyze,
            'visual_metrics': analyze_image, 'semantic_match': match_text, 'score': score,
            'index_knowledge': index_knowledge, 'retrieve_outreach': retrieve_outreach, 'prepare_outreach': prepare_outreach}
