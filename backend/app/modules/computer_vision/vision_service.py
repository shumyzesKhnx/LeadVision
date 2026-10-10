"""Deterministic pixel metrics, never a website-quality or buying-intent score."""
from io import BytesIO
from uuid import uuid5, NAMESPACE_URL
import copy
import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import select
from app.modules.foundation.hashing import snapshot_hash
from app.modules.foundation.storage import ArtifactStorage
from app.modules.foundation.errors import AppError
from app.modules.computer_vision.vision_config import VisionConfig, vision_identity
from app.modules.evidence.evidence_model import Evidence
from app.modules.computer_vision.visual_analysis_model import VisualAnalysis
from app.modules.computer_vision.visual_analysis_schema import VisualMetrics, VisualResult
from app.modules.processing.jobs_repository import run_for_job
from app.modules.evidence.evidence_service import read_verified
from app.modules.evidence.image_validation_service import validate_image
from app.modules.processing.workflow_service import StageResult, StageFailure

LIMITATIONS = [
    'Edges are pixel boundaries, not text density or CTA recognition.',
    'Brightness is not text/background contrast or a WCAG assessment.',
    'Flat areas may contain illustrations; this is not true whitespace.',
    'These measurements do not establish design quality, usability, age or buying intent.',
]


def measure(content, config=None, checkpoint=lambda: None):
    config = VisionConfig.model_validate(config or {})
    metadata, _ = validate_image(content)
    checkpoint()
    with Image.open(BytesIO(content), formats=['PNG', 'JPEG']) as source:
        oriented = ImageOps.exif_transpose(source)
        if 'A' in oriented.getbands() or 'transparency' in oriented.info:
            rgba = oriented.convert('RGBA')
            background = Image.new('RGBA', rgba.size, 'white')
            background.alpha_composite(rgba)
            working = background.convert('RGB')
        else:
            working = oriented.convert('RGB')
        rgb = np.asarray(working, dtype=np.uint8).copy()
    factor = min(1, config.max_width / metadata['width'], config.max_height / metadata['height'])
    width, height = max(1, round(metadata['width'] * factor)), max(1, round(metadata['height'] * factor))
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    if (width, height) != (metadata['width'], metadata['height']):
        rgb = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, config.canny_low, config.canny_high, apertureSize=3, L2gradient=True)
    checkpoint()
    pixels = width * height
    brightness = (np.histogram(gray, bins=16, range=(0, 256))[0] / pixels).tolist()
    histograms = {name: (np.histogram(rgb[:, :, index], bins=8, range=(0, 256))[0] / pixels).tolist()
                  for index, name in enumerate(('red', 'green', 'blue'))}
    quantized = rgb.astype(np.uint16) // 32
    codes = quantized[:, :, 0] * 64 + quantized[:, :, 1] * 8 + quantized[:, :, 2]
    counts = np.bincount(codes.ravel(), minlength=512)
    # Frequency descending; quantized RGB code ascending resolves every tie.
    top = sorted(range(512), key=lambda code: (-int(counts[code]), code))[:5]
    dominant = [{'rgb_bin_center': [int((code // 64) * 32 + 16), int(((code // 8) % 8) * 32 + 16),
                                   int((code % 8) * 32 + 16)], 'fraction': float(counts[code] / pixels)}
                for code in top if counts[code]]
    flat_area = 0
    for y in range(0, height, config.tile_size):
        checkpoint()
        for x in range(0, width, config.tile_size):
            tile = gray[y:y + config.tile_size, x:x + config.tile_size]
            if float(tile.std()) <= config.low_variation_std:
                flat_area += tile.size
    return VisualMetrics(edge_density=float(np.count_nonzero(edges) / pixels),
        brightness_mean=float(gray.mean() / 255), brightness_std=float(gray.std() / 255),
        brightness_histogram=brightness, rgb_histograms=histograms, dominant_colors=dominant,
        low_variation_area_fraction=flat_area / pixels, original_width=metadata['original_width'],
        original_height=metadata['original_height'], oriented_width=metadata['width'], oriented_height=metadata['height'],
        working_width=width, working_height=height, orientation_applied=metadata['orientation_applied']).model_dump()


def unavailable(reason, evidence_id=None):
    return StageResult(state='warning', output={'visual_result': VisualResult(available=False, reason=reason,
        limitations=LIMITATIONS).model_dump(), 'provenance': {'evidence_id': evidence_id, 'identity': vision_identity()}},
        warnings=[reason])


def analyze(context, snapshot, outputs):
    context.checkpoint()
    if snapshot.get('vision') != vision_identity():
        raise StageFailure('VISION_CONFIG_CHANGED')
    image = outputs.get('acquire_image', {})
    evidence_id = image.get('evidence_id')
    if not image.get('available'):
        return unavailable('IMAGE_UNUSABLE' if evidence_id else 'IMAGE_MISSING', evidence_id)
    with context.worker.database.sessions() as session:
        evidence = session.get(Evidence, evidence_id)
        if evidence is None:
            return unavailable('IMAGE_MISSING')
        if not evidence.usable:
            return unavailable('IMAGE_UNUSABLE', evidence_id)
        metadata, revision = copy.deepcopy(evidence.metadata_json), evidence.revision
    key = snapshot_hash({'sha256': metadata['sha256'], 'identity': snapshot['vision'], 'review_revision': revision})
    with context.worker.database.sessions() as session:
        cached = session.scalar(select(VisualAnalysis).where(VisualAnalysis.input_hash == key)
                                .order_by(VisualAnalysis.created_at.desc(), VisualAnalysis.id.desc()).limit(1))
        cached_result = copy.deepcopy(cached.result) if cached else None
        cached_id = cached.id if cached else None
    try:
        content = read_verified(ArtifactStorage(context.worker.settings.data_dir), metadata)
        metrics = cached_result['metrics'] if cached_result else measure(content, snapshot['vision']['config'], context.checkpoint)
    except AppError as error:
        return unavailable(error.code, evidence_id)
    except (OSError, ValueError, cv2.error):
        return unavailable('INVALID_IMAGE', evidence_id)
    context.checkpoint()
    with context.worker.database.sessions() as session:
        evidence = session.get(Evidence, evidence_id)
        if evidence is None or not evidence.usable or evidence.revision != revision:
            return unavailable('IMAGE_REVIEW_CHANGED', evidence_id)
    result = VisualResult(available=True, metrics=VisualMetrics.model_validate(metrics), limitations=LIMITATIONS)
    return StageResult(output={'visual_result': result.model_dump(), 'provenance': {
        'evidence_id': evidence_id, 'evidence_revision': revision, 'image_sha256': metadata['sha256'],
        'input_hash': key, 'identity': snapshot['vision'], 'cache_hit': cached_id is not None,
        'cache_origin_analysis_id': cached_id, 'viewport': metadata.get('viewport'),
        'collected_at': image.get('collected_at')}}, usable=True)


def persist_visual(session, job, name, result):
    if name != 'visual_metrics' or 'visual_result' not in result.output:
        return
    run = run_for_job(session, job.id)
    visual_id = str(uuid5(NAMESPACE_URL, f'leadvision:{run.id}:visual'))
    if session.get(VisualAnalysis, visual_id):
        return
    provenance = result.output['provenance']
    if result.output['visual_result']['available']:
        evidence = session.get(Evidence, provenance['evidence_id'])
        if evidence is None or not evidence.usable or evidence.revision != provenance['evidence_revision']:
            raise StageFailure('IMAGE_REVIEW_CHANGED')
    session.add(VisualAnalysis(id=visual_id, run_id=run.id, evidence_id=provenance.get('evidence_id'),
        input_hash=provenance.get('input_hash') or snapshot_hash({'run_id': run.id, 'result': result.output['visual_result']}),
        result=result.output['visual_result'], provenance=provenance))
