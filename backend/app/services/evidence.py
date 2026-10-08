"""Durable uploads, transactional attachment, evidence review and file cleanup."""
from datetime import datetime, timedelta, timezone
import secrets
from uuid import uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import select, func
from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.hashing import content_hash
from app.core.revisions import check_revision
from app.core.storage import ArtifactStorage
from app.models.evidence import Evidence, SavedEvidenceUpload
from app.models.job import Job
from app.models.maintenance import FileCleanupTask, WorkerState
from app.db.repositories.jobs import run_for_job
from app.schemas.evidence import EvidenceResponse, SavedEvidenceReceipt
from app.services.leads import require_lead
from app.services.campaign import require_campaign
from app.services.activity import record_activity
from app.services.file_cleanup import queue_cleanup, perform_cleanup
from app.services.text_extraction import validate_saved_text, MAX_TEXT_BYTES
from app.services.image_validation import validate_image, MAX_IMAGE_BYTES
from app.services.workflow import StageResult, StageFailure


def artifact_keys(manifest):
    return [item[key] for kind in ('text', 'image') if (item := manifest.get(kind))
            for key in ('artifact_key', 'thumbnail_key') if item.get(key)]


def create_upload(database, storage, settings, lead_id, metadata, text_bytes, image_bytes):
    # Decode outside a database transaction. Originals are preserved byte-for-byte.
    manifest = metadata.model_dump(mode='json')
    if metadata.collected_at:
        manifest['collected_at'] = metadata.collected_at.isoformat().replace('+00:00', 'Z')
    warnings = []
    files = []
    if text_bytes is not None:
        text, info = validate_saved_text(text_bytes)
        key = f'evidence/{uuid4().hex}.txt'
        manifest['text'] = {**info, 'artifact_key': key, 'sha256': content_hash(text_bytes),
                            'bytes': len(text_bytes), 'excerpt': text[:1000]}
        files.append((key, text_bytes, MAX_TEXT_BYTES))
        if info['truncated']:
            warnings.append('TEXT_TRUNCATED')
        if len(text) < 1000 and any(phrase in text.casefold() for phrase in ('access denied', 'verify you are human', 'captcha', 'enable cookies')):
            warnings.append('TEXT_MAY_BE_BLOCKED')
    else:
        warnings.append('TEXT_UNAVAILABLE')
    if image_bytes is not None:
        try:
            info, thumbnail = validate_image(image_bytes)
        except AppError as error:
            if text_bytes is None:
                raise
            warnings.append(error.code)
        else:
            key = f"evidence/{uuid4().hex}.{'png' if info['format'] == 'PNG' else 'jpg'}"
            thumb_key = f'evidence/{uuid4().hex}.jpg'
            manifest['image'] = {**info, 'artifact_key': key, 'thumbnail_key': thumb_key,
                                 'sha256': content_hash(image_bytes), 'thumbnail_sha256': content_hash(thumbnail),
                                 'bytes': len(image_bytes), 'thumbnail_bytes': len(thumbnail),
                                 'viewport': None, 'browser': None}
            files.extend([(key, image_bytes, MAX_IMAGE_BYTES), (thumb_key, thumbnail, MAX_IMAGE_BYTES)])
    if 'image' not in manifest:
        warnings.append('IMAGE_UNAVAILABLE')
    if not files:
        raise AppError('EVIDENCE_REQUIRED', 'Upload a text file, an image, or both.', 422)
    manifest['warnings'] = warnings
    token = secrets.token_urlsafe(32)
    now = utc_now()
    expires = (datetime.now(timezone.utc) + timedelta(seconds=settings.saved_upload_ttl_seconds)).isoformat().replace('+00:00', 'Z')
    with database.transaction(immediate=True) as session:
        lead = require_lead(session, lead_id)
        require_campaign(session, lead.campaign_id, for_work=True)
        pending = session.scalar(select(func.count()).select_from(SavedEvidenceUpload).where(
            SavedEvidenceUpload.lead_id == lead_id, SavedEvidenceUpload.state.in_(['staging', 'ready'])))
        if pending >= 20:
            raise AppError('UPLOAD_LIMIT', 'Use or wait for expiry of earlier uploads before adding more.', 409)
        upload = SavedEvidenceUpload(lead_id=lead_id, token_hash=content_hash(token.encode()),
                                     source_mode=metadata.source_mode, manifest=manifest, imported_at=now, expires_at=expires)
        session.add(upload)
        session.flush()
        upload_id = upload.id
    # Reservation survives a crash; expiry cleanup knows every possibly written key.
    try:
        for key, content, limit in files:
            storage.write_to(key, content, max_bytes=limit)
        with database.transaction(immediate=True) as session:
            upload = session.get(SavedEvidenceUpload, upload_id)
            if upload is None or upload.state != 'staging':
                raise AppError('UPLOAD_UNAVAILABLE', 'This upload is no longer available.', 409)
            upload.state = 'ready'
            lead = require_lead(session, lead_id)
            campaign = require_campaign(session, lead.campaign_id, for_work=True)
            record_activity(session, action='evidence.uploaded', origin='api', agency_id=campaign.agency_id,
                            campaign_id=campaign.id, lead_id=lead_id, event_key=f'upload:{upload_id}:ready',
                            new_value={'upload_id': upload_id, 'source_mode': metadata.source_mode,
                                       'text_available': 'text' in manifest, 'image_available': 'image' in manifest})
    except Exception as error:
        with database.transaction(immediate=True) as session:
            upload = session.get(SavedEvidenceUpload, upload_id)
            if upload and upload.state == 'staging':
                expire_upload(session, storage, upload)
            else:
                # A deletion/expiry may have cleaned an earlier write before this
                # writer returned. Queue another durable pass after its last write.
                for key in artifact_keys(manifest):
                    queue_cleanup(session, storage, artifact_key=key, reason='Unattached saved evidence write')
        if isinstance(error, AppError):
            raise
        raise AppError('ARTIFACT_STORAGE_UNAVAILABLE', 'The upload could not be saved. Try again.', 503) from None
    return SavedEvidenceReceipt(upload_token=token, source_mode=metadata.source_mode, imported_at=now,
                                expires_at=expires, text_available='text' in manifest,
                                image_available='image' in manifest, warnings=warnings)


def require_upload(session, lead_id, body, retry_of=None):
    upload = session.scalar(select(SavedEvidenceUpload).where(
        SavedEvidenceUpload.token_hash == content_hash(body.upload_token.encode()), SavedEvidenceUpload.lead_id == lead_id))
    if upload is None:
        raise AppError('UPLOAD_NOT_FOUND', 'Saved evidence token not found for this lead.', 404)
    if upload.state == 'expired' or (upload.state != 'attached' and upload.expires_at <= utc_now()):
        raise AppError('UPLOAD_EXPIRED', 'Upload new saved evidence; this token has expired.', 409)
    if upload.state == 'staging':
        raise AppError('UPLOAD_NOT_READY', 'The upload has not finished saving.', 409)
    if upload.source_mode != body.mode:
        raise AppError('EVIDENCE_MODE_MISMATCH', 'Choose the source mode used for this upload.', 422)
    if body.include_supporting_pages:
        raise AppError('SAVED_PAGES_UNAVAILABLE', 'Saved evidence contains one text/image pair; disable supporting pages.', 422)
    if upload.state == 'attached':
        previous = session.get(Job, retry_of) if retry_of else None
        if previous is None or previous.input_snapshot.get('saved_upload_id') != upload.id:
            raise AppError('UPLOAD_CONSUMED', 'This token belongs to another job. Retry that job or upload again.', 409)
    return upload


def attach_upload(upload, job_id):
    if upload.state == 'ready':
        upload.state = 'attached'
        upload.attached_job_id = job_id


def read_verified(storage, metadata, *, thumbnail=False):
    key = metadata['thumbnail_key' if thumbnail else 'artifact_key']
    limit = MAX_IMAGE_BYTES if thumbnail or metadata.get('format') else MAX_TEXT_BYTES
    try:
        with storage.resolve(key).open('rb') as file:
            content = file.read(limit + 1)
    except (OSError, ValueError):
        raise AppError('ARTIFACT_UNAVAILABLE', 'The saved artifact is unavailable.', 503) from None
    expected = metadata['thumbnail_sha256' if thumbnail else 'sha256']
    if len(content) > limit or content_hash(content) != expected:
        raise AppError('ARTIFACT_INTEGRITY_ERROR', 'The saved artifact changed. Upload a new copy.', 409)
    return content


def saved_stage(context, snapshot, kind):
    context.checkpoint()
    if not snapshot.get('saved_upload_id'):
        raise StageFailure('STAGE_NOT_IMPLEMENTED')
    manifest = snapshot['saved_manifest']
    item = manifest.get(kind)
    if item is None:
        return StageResult(state='warning', output={'available': False, 'source_mode': snapshot['request']['mode']},
                           warnings=[f'{kind.upper()}_UNAVAILABLE'])
    with context.worker.database.sessions() as session:
        run_id = run_for_job(session, context.job_id).id
    evidence_id = str(uuid5(NAMESPACE_URL, f'leadvision:{run_id}:{kind}'))
    output = {'available': True, 'evidence_id': evidence_id, 'source_mode': snapshot['request']['mode'],
              'source_label': 'Cached' if snapshot['request']['mode'] == 'cached' else 'Uploaded',
              'collected_at': manifest.get('collected_at'), 'imported_at': snapshot['saved_imported_at'],
              'sha256': item['sha256']}
    review = snapshot.get('saved_reviews', {}).get(kind)
    if review and not review['usable']:
        output['available'] = False
        return StageResult(state='warning', output=output, warnings=['EVIDENCE_MARKED_UNUSABLE'])
    storage = ArtifactStorage(context.worker.settings.data_dir)
    try:
        content = read_verified(storage, item)
        if kind == 'text':
            text, _ = validate_saved_text(content)
        else:
            read_verified(storage, item, thumbnail=True)
    except AppError as error:
        if kind == 'image':
            output.update(available=False, unavailable_code=error.code)
            return StageResult(state='warning', output=output, warnings=[error.code, 'IMAGE_UNAVAILABLE'])
        raise StageFailure(error.code) from None
    context.checkpoint()
    if kind == 'text':
        output.update(text=text, title=manifest.get('title'), truncated=item['truncated'])
    else:
        output.update(width=item['width'], height=item['height'], image_url=f'/api/v1/artifacts/{evidence_id}/image')
    return StageResult(output=output, usable=True, warnings=manifest['warnings'] if kind == 'text' else [])


def persist_stage_evidence(session, job, stage_name, result):
    """Called inside the worker's stage/result/activity transaction."""
    if stage_name not in {'acquire_text', 'acquire_image'} or not job.input_snapshot.get('saved_upload_id'):
        return
    if not result.output.get('evidence_id'):
        return
    kind = 'text' if stage_name == 'acquire_text' else 'image'
    run = run_for_job(session, job.id)
    evidence_id = str(uuid5(NAMESPACE_URL, f'leadvision:{run.id}:{kind}'))
    if result.output.get('evidence_id') != evidence_id:
        raise ValueError('Evidence stage output does not match its owner.')
    if session.get(Evidence, evidence_id):
        return
    manifest = job.input_snapshot['saved_manifest']
    review = job.input_snapshot.get('saved_reviews', {}).get(kind, {})
    session.add(Evidence(id=evidence_id, run_id=run.id, saved_upload_id=job.input_snapshot['saved_upload_id'],
                         kind=kind, source_mode=job.request_body['mode'], original_url=manifest.get('original_url'),
                         collected_at=manifest.get('collected_at'), imported_at=job.input_snapshot['saved_imported_at'],
                         metadata_json=manifest[kind], usable=review.get('usable', True) and result.output['available'],
                         review_reason=review.get('reason') or result.output.get('unavailable_code')))


def require_evidence(session, evidence_id):
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise AppError('EVIDENCE_NOT_FOUND', 'Evidence not found.', 404)
    from app.models.analysis_run import AnalysisRun
    require_lead(session, session.get(AnalysisRun, evidence.run_id).lead_id)
    return evidence


def evidence_response(evidence):
    public = {key: value for key, value in evidence.metadata_json.items() if key not in {'artifact_key', 'thumbnail_key'}}
    return EvidenceResponse(id=evidence.id, run_id=evidence.run_id, kind=evidence.kind,
        source_mode=evidence.source_mode, source_label='Cached' if evidence.source_mode == 'cached' else 'Uploaded',
        original_url=evidence.original_url, collected_at=evidence.collected_at, imported_at=evidence.imported_at,
        metadata=public, usable=evidence.usable, review_reason=evidence.review_reason, revision=evidence.revision,
        updated_at=evidence.updated_at,
        image_url=f'/api/v1/artifacts/{evidence.id}/image' if evidence.kind == 'image' else None,
        thumbnail_url=f'/api/v1/artifacts/{evidence.id}/thumbnail' if evidence.kind == 'image' else None)


def review(session, evidence, body, expected):
    check_revision(evidence.revision, expected)
    if evidence.usable == body.usable and evidence.review_reason == body.reason:
        return evidence_response(evidence)
    evidence.usable, evidence.review_reason = body.usable, body.reason
    evidence.revision += 1
    evidence.updated_at = utc_now()
    from app.models.analysis_run import AnalysisRun
    lead = require_lead(session, session.get(AnalysisRun, evidence.run_id).lead_id)
    campaign = require_campaign(session, lead.campaign_id)
    record_activity(session, action='evidence.reviewed', origin='api', agency_id=campaign.agency_id,
                    campaign_id=campaign.id, lead_id=lead.id,
                    new_value={'evidence_id': evidence.id, 'usable': evidence.usable, 'revision': evidence.revision})
    return evidence_response(evidence)


def expire_upload(session, storage, upload):
    for key in artifact_keys(upload.manifest):
        queue_cleanup(session, storage, artifact_key=key, reason='Expired or failed saved evidence upload')
        target = storage.resolve(key)
        for temporary in target.parent.glob(f'.staged-{target.stem}-*'):
            queue_cleanup(session, storage, artifact_key=f'evidence/{temporary.name}', reason='Abandoned saved evidence write')
    upload.state = 'expired'


def housekeeping(database, storage):
    with database.transaction(immediate=True) as session:
        if session.get(WorkerState, 1).maintenance_requested:
            return
        uploads = session.scalars(select(SavedEvidenceUpload).where(
            SavedEvidenceUpload.state.in_(['staging', 'ready']), SavedEvidenceUpload.expires_at <= utc_now()).limit(20))
        for upload in uploads:
            expire_upload(session, storage, upload)
        from app.models.business_analysis import ModelDiagnostic
        diagnostics = list(session.scalars(select(ModelDiagnostic).where(ModelDiagnostic.expires_at <= utc_now()).limit(20)))
        for diagnostic in diagnostics:
            queue_cleanup(session, storage, artifact_key=diagnostic.artifact_key, reason='Expired model diagnostic')
            session.delete(diagnostic)
        tasks = list(session.scalars(select(FileCleanupTask.id).where(
            FileCleanupTask.state.in_(['pending', 'failed']), FileCleanupTask.attempts < 3).limit(20)))
    for task_id in tasks:
        with database.transaction(immediate=True) as session:
            if session.get(WorkerState, 1).maintenance_requested:
                return
            perform_cleanup(session, storage, task_id)


def queue_lead_artifacts(session, storage, lead_id):
    count = 0
    from app.models.business_analysis import ModelDiagnostic
    for diagnostic in session.scalars(select(ModelDiagnostic).where(ModelDiagnostic.lead_id == lead_id)):
        queue_cleanup(session, storage, artifact_key=diagnostic.artifact_key, reason='Deleted lead model diagnostic')
        count += 1
    for upload in session.scalars(select(SavedEvidenceUpload).where(SavedEvidenceUpload.lead_id == lead_id)):
        for key in artifact_keys(upload.manifest):
            queue_cleanup(session, storage, artifact_key=key, reason='Deleted lead saved evidence')
            count += 1
    return count
