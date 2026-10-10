"""Collect live pages and screenshots, reserving artifact ownership before writes."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from uuid import uuid4, uuid5, NAMESPACE_URL
from app.modules.foundation.clock import utc_now
from app.modules.foundation.hashing import content_hash
from app.modules.foundation.storage import ArtifactStorage
from app.modules.processing.jobs_repository import run_for_job
from app.modules.evidence import safe_http_client as safe_http
from app.modules.evidence import safe_browser_client as safe_browser
from app.modules.evidence.evidence_model import Evidence
from app.modules.evidence.live_artifact_model import LiveArtifact
from app.modules.evidence.text_extraction_service import extract_html
from app.modules.evidence.image_validation_service import validate_image, MAX_IMAGE_BYTES
from app.modules.processing.workflow_service import StageResult, StageFailure


class RobotsPolicy:
    def __init__(self, checkpoint):
        self.checkpoint = checkpoint; self.cache = {}; self.warnings = set()
    def authorize(self, url):
        parsed = urlsplit(url); origin = urlunsplit((parsed.scheme, parsed.netloc, '', '', ''))
        if origin not in self.cache:
            parser = RobotFileParser()
            try:
                page = safe_http.fetch(origin + '/robots.txt', self.checkpoint, html=False, limit=50000)
                parser.parse(page.body.decode('utf-8', errors='replace').splitlines())
            except StageFailure as error:
                if error.code in {'UNSAFE_DESTINATION', 'ACCESS_DENIED', 'JOB_CANCELLED', 'JOB_INTERRUPTED', 'JOB_TIMEOUT', 'STAGE_TIMEOUT'}: raise
                self.warnings.add('ROBOTS_UNAVAILABLE'); parser = None
            self.cache[origin] = parser
        parser = self.cache[origin]
        if parser and not parser.can_fetch('LeadVision', url): raise StageFailure('ROBOTS_DISALLOWED')


def reserve(context, kind, metadata, files, url):
    storage = ArtifactStorage(context.worker.settings.data_dir)
    for key, content, _ in files: metadata[key + '_sha256'] = content_hash(content) if key != 'artifact' else metadata.get('sha256', content_hash(content))
    metadata.pop('artifact_sha256', None)
    writes = []
    for name, content, limit in files:
        key = 'evidence/' + uuid4().hex + ('.txt' if kind == 'text' else ('.png' if name == 'artifact' else '.jpg'))
        metadata[name + '_key'] = key; writes.append((key, content, limit))
    now = utc_now(); expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
    with context.worker.database.transaction(immediate=True) as session:
        run = run_for_job(session, context.job_id)
        reservation = LiveArtifact(run_id=run.id, lead_id=run.lead_id, kind=kind, metadata_json=metadata,
            original_url=url, collected_at=now, expires_at=expires)
        session.add(reservation); session.flush(); reservation_id = reservation.id; run_id = run.id
    # A crash cannot orphan untracked files: expiry or lead deletion knows the keys.
    for key, content, limit in writes:
        context.checkpoint(); storage.write_to(key, content, max_bytes=limit)
    with context.worker.database.transaction(immediate=True) as session:
        session.get(LiveArtifact, reservation_id).state = 'ready'
    return reservation_id, str(uuid5(NAMESPACE_URL, f'leadvision:{run_id}:{kind}')), now


def collect_text(context, snapshot, outputs):
    policy = RobotsPolicy(context.checkpoint)
    page = safe_http.fetch(snapshot['lead']['normalized_url'], context.checkpoint, authorize=policy.authorize)
    homepage = extract_html(page.body, page.url, page.headers.get('content-type', ''))
    sources = []; pieces = []; warnings = set(policy.warnings)
    pages = [(page, homepage)]
    if snapshot['request']['include_supporting_pages']:
        for url in homepage['supporting_urls']:
            try:
                def authorize_support(target):
                    if urlsplit(target).hostname != urlsplit(page.url).hostname: raise StageFailure('SUPPORT_PAGE_HOST_CHANGED')
                    policy.authorize(target)
                support = safe_http.fetch(url, context.checkpoint, authorize=authorize_support)
                if urlsplit(support.url).hostname != urlsplit(page.url).hostname:
                    warnings.add('SUPPORT_PAGE_HOST_CHANGED'); continue
                pages.append((support, extract_html(support.body, support.url, support.headers.get('content-type', ''))))
            except StageFailure as error:
                if error.code in {'JOB_CANCELLED', 'JOB_INTERRUPTED', 'JOB_TIMEOUT', 'STAGE_TIMEOUT'}: raise
                warnings.add('SUPPORT_PAGE_UNAVAILABLE')
    for source, extracted in pages:
        piece = extracted['text']
        if piece:
            offset = sum(len(item) + 2 for item in pieces)
            pieces.append(piece)
            sources.append({'url': source.url, 'title': extracted['title'], 'start': offset,
                'end': offset + len(piece), 'html_sha256': content_hash(source.body),
                'excerpt': piece[:500], 'truncated': extracted['truncated']})
    text = '\n\n'.join(pieces)
    truncated = len(text) > 26000 or any(item['truncated'] for item in sources)
    text = text[:26000]
    for source in sources:
        source['truncated'] |= source['end'] > len(text)
        source['end'] = min(source['end'], len(text))
    sources = [source for source in sources if source['start'] < len(text)]
    if not text: raise StageFailure('EMPTY_TEXT')
    if any(phrase in text[:1500].casefold() for phrase in ('access denied', 'verify you are human', 'captcha', 'enable cookies')):
        raise StageFailure('ACCESS_DENIED')
    if any(phrase in text[:1500].casefold() for phrase in ('cookie consent','accept all cookies')): warnings.add('CONSENT_MAY_OBSCURE_PAGE')
    content = text.encode('utf-8')
    metadata = {'sha256': content_hash(content), 'bytes': len(content), 'characters': len(text),
        'truncated': truncated, 'title': homepage['title'], 'pages': sources, 'final_url': page.url,
        'excerpt': text[:1000], 'collector_version': 'live-evidence-v1'}
    reservation, evidence_id, now = reserve(context, 'text', metadata, [('artifact', content, 1_000_000)], page.url)
    if truncated: warnings.add('TEXT_TRUNCATED')
    return StageResult(output={'available': True, 'evidence_id': evidence_id, 'live_reservation_id': reservation,
        'source_mode': 'live', 'source_label': 'Live', 'collected_at': now, 'imported_at': now,
        'text': text, 'title': homepage['title'], 'truncated': truncated, 'sha256': content_hash(content),
        'final_url': page.url}, warnings=sorted(warnings | policy.warnings)[:10], usable=True)


def collect_image(context, snapshot, outputs):
    text = outputs.get('acquire_text', {})
    if not text.get('available'):
        return StageResult(state='warning', output={'available': False}, warnings=['IMAGE_UNAVAILABLE'])
    policy = RobotsPolicy(context.checkpoint)
    original, browser_info, warnings = safe_browser.capture(text['final_url'], context.checkpoint, policy.authorize,
        channel=context.worker.settings.browser_channel)
    info, thumbnail = validate_image(original)
    metadata = {**info, **browser_info, 'sha256': content_hash(original), 'bytes': len(original),
        'thumbnail_sha256': content_hash(thumbnail), 'thumbnail_bytes': len(thumbnail), 'collector_version': 'live-evidence-v1'}
    reservation, evidence_id, now = reserve(context, 'image', metadata,
        [('artifact', original, MAX_IMAGE_BYTES), ('thumbnail', thumbnail, MAX_IMAGE_BYTES)], browser_info['final_url'])
    return StageResult(output={'available': True, 'evidence_id': evidence_id, 'live_reservation_id': reservation,
        'source_mode': 'live', 'source_label': 'Live', 'collected_at': now, 'imported_at': now,
        'sha256': content_hash(original), 'width': info['width'], 'height': info['height'],
        'image_url': f'/api/v1/artifacts/{evidence_id}/image'}, warnings=sorted(set(warnings) | policy.warnings)[:10], usable=True)


def persist(session, job, name, result):
    if name not in ('acquire_text', 'acquire_image') or 'live_reservation_id' not in result.output: return
    reservation = session.get(LiveArtifact, result.output['live_reservation_id'])
    run = run_for_job(session, job.id)
    if reservation is None or reservation.run_id != run.id or reservation.state != 'ready':
        raise StageFailure('ARTIFACT_UNAVAILABLE')
    evidence_id = str(uuid5(NAMESPACE_URL, f'leadvision:{run.id}:{reservation.kind}'))
    if evidence_id != result.output['evidence_id']: raise StageFailure('INVALID_STAGE_OUTPUT')
    session.add(Evidence(id=evidence_id, run_id=run.id, saved_upload_id=None, kind=reservation.kind,
        source_mode='live', original_url=reservation.original_url, collected_at=reservation.collected_at,
        imported_at=reservation.collected_at, metadata_json=reservation.metadata_json))
    reservation.state = 'attached'
