"""Save reviewed agency facts without making model work part of an API transaction."""
from sqlalchemy import select, func
from app.modules.agency.agency_service import require_workspace
from app.modules.foundation.clock import utc_now
from app.modules.foundation.errors import AppError
from app.modules.foundation.hashing import snapshot_hash
from app.modules.foundation.revisions import check_revision
from app.modules.processing.activity_service import record_activity
from app.modules.processing.job_model import Job
from app.modules.processing import jobs_repository
from app.modules.processing.jobs_service import require_worker
from app.modules.knowledge.knowledge_model import KnowledgeDocument, KnowledgeVersion, KnowledgeChunk
from app.modules.knowledge.knowledge_schema import KnowledgeResponse, KnowledgeVersionResponse, IndexReceipt


def require_document(session, document_id):
    agency = require_workspace(session)
    row = session.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == str(document_id), KnowledgeDocument.agency_id == agency.id))
    if row is None: raise AppError('KNOWLEDGE_NOT_FOUND', 'Knowledge document not found.', 404)
    return row


def version_response(row, *, include_text=False):
    return KnowledgeVersionResponse(**{key: getattr(row, key) for key in ('id', 'version', 'title', 'document_type', 'demo', 'content_hash', 'created_at')}, text=row.text if include_text else None)


def response(session, row, *, detail=False):
    version = session.get(KnowledgeVersion, row.current_version_id)
    job = session.scalar(select(Job).where(Job.agency_id == row.agency_id, Job.kind == 'knowledge_index', Job.scope == f'knowledge:{row.id}')
                         .order_by(Job.queued_at.desc(), Job.id.desc()).limit(1))
    current = job and job.input_snapshot['version_id'] == version.id and job.input_snapshot['document_revision'] == row.revision
    status = job.status if current else 'not_indexed'
    count = session.scalar(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.job_id == job.id)) if current and job.status == 'completed' else 0
    history = list(session.scalars(select(KnowledgeVersion).where(KnowledgeVersion.document_id == row.id).order_by(KnowledgeVersion.version.desc()))) if detail else []
    return KnowledgeResponse(**{key: getattr(row, key) for key in ('id','agency_id','revision','active','approved','created_at','updated_at')},
                             current_version=version_response(version, include_text=detail), index_status=status,
                             index_job_id=job.id if current else None, chunk_count=count,
                             versions=[version_response(item) for item in history])


def save_version(session, row, values, number):
    version = KnowledgeVersion(document_id=row.id, version=number, content_hash=snapshot_hash(values), **values)
    session.add(version); session.flush()
    row.current_version_id = version.id


def create(session, body):
    agency = require_workspace(session)
    if session.scalar(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.agency_id == agency.id)) >= 100:
        raise AppError('KNOWLEDGE_LIMIT', 'This local workspace supports up to 100 knowledge documents.', 409)
    row = KnowledgeDocument(agency_id=agency.id, approved=body.approved)
    session.add(row); session.flush()
    save_version(session, row, body.model_dump(exclude={'approved'}), 1)
    session.flush()
    record_activity(session, action='knowledge.created', origin='api', agency_id=agency.id, new_value={'document_id':row.id,'version_id':row.current_version_id})
    return response(session, row, detail=True)


def edit(session, document_id, body, expected):
    row = require_document(session, document_id)
    check_revision(row.revision, expected)
    old = session.get(KnowledgeVersion, row.current_version_id)
    changes = body.model_dump(exclude_unset=True)
    content = {key:getattr(old,key) for key in ('title','document_type','text','demo')}
    revised = {**content, **{key:value for key,value in changes.items() if key in content}}
    changed = revised != content
    if not changed and all(value == getattr(row, key) for key,value in changes.items() if key in {'approved','active'}):
        return response(session, row, detail=True)
    if changed:
        if old.version >= 100: raise AppError('KNOWLEDGE_VERSION_LIMIT', 'This document has reached its 100-version limit.', 409)
        save_version(session, row, revised, old.version + 1)
        row.approved = False  # Editing facts always requires a separate review of the new version.
    else:
        row.approved = changes.get('approved', row.approved)
    row.active = changes.get('active', row.active)
    # A real PATCH invalidates indexes by pinning the new document revision.
    row.revision += 1; row.updated_at = utc_now()
    session.flush()
    record_activity(session, action='knowledge.updated', origin='api', agency_id=row.agency_id, new_value={'document_id':row.id,'revision':row.revision,'content_changed':changed,'approved':row.approved,'active':row.active})
    return response(session, row, detail=True)


def eligible_job(session, job):
    snapshot = job.input_snapshot
    row = session.get(KnowledgeDocument, snapshot.get('document_id'))
    return bool(row and row.agency_id == job.agency_id and row.active and row.approved and
                row.current_version_id == snapshot['version_id'] and row.revision == snapshot['document_revision'])


def index_receipt(job):
    return IndexReceipt(job_id=job.id,status=job.status,poll_url=f'/api/v1/jobs/{job.id}',document_id=job.input_snapshot['document_id'],version_id=job.input_snapshot['version_id'])


def submit_index(session, settings, document_id, version_id, key, identity, *, retry_of=None):
    from app.modules.processing.job_model import JobStage
    row = require_document(session, document_id)
    scope = f'knowledge:{row.id}'
    request = {'version_id': str(version_id)}
    fingerprint = snapshot_hash({'request':request,'retry_of_id':retry_of})
    prior = jobs_repository.replay(session, row.agency_id, scope, key)
    if prior:
        if prior.request_hash != fingerprint: raise AppError('IDEMPOTENCY_CONFLICT','This key belongs to a different indexing request.',409)
        return index_receipt(prior)
    if row.current_version_id != str(version_id): raise AppError('KNOWLEDGE_VERSION_CHANGED','Reload the current document before indexing.',409)
    if not row.active or not row.approved: raise AppError('KNOWLEDGE_NOT_APPROVED','Activate and approve this version before indexing.',409)
    if not identity: raise AppError('EMBEDDING_UNAVAILABLE','The local embedding model is unavailable. The document remains saved.',503)
    require_worker(session, settings)
    if session.scalar(select(Job.id).where(Job.agency_id == row.agency_id,Job.scope == scope,Job.status.in_(['queued','running']))):
        raise AppError('KNOWLEDGE_INDEX_ACTIVE','This document already has queued or running indexing.',409)
    snapshot = {'snapshot_version':1,'document_id':row.id,'version_id':row.current_version_id,
                'document_revision':row.revision,'models':{'embedding':{'status':'available','identity':identity}},'request':request}
    job = Job(agency_id=row.agency_id,lead_id=None,kind='knowledge_index',request_body=request,input_snapshot=snapshot,
              request_hash=fingerprint,idempotency_key=key,scope=scope,retry_of_id=retry_of)
    session.add(job); session.flush()
    for ordinal,name in enumerate(('index_knowledge','finalize')):
        session.add(JobStage(job_id=job.id,name=name,ordinal=ordinal,input_hash=snapshot_hash(snapshot),required=name!='finalize'))
    record_activity(session,action='knowledge_index.queued',origin='api',agency_id=row.agency_id,new_value={'job_id':job.id,'document_id':row.id,'version_id':row.current_version_id},event_key=f'job:{job.id}:queued')
    return index_receipt(job)
