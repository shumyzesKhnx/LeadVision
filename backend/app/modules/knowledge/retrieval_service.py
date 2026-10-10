"""Return at most three eligible source passages; empty results are explicit."""
from types import SimpleNamespace
import numpy as np
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import aliased
from app.modules.agency.agency_service import require_workspace
from app.modules.agency.service_model import Service
from app.modules.foundation.errors import AppError
from app.modules.foundation.hashing import snapshot_hash
from app.modules.knowledge.knowledge_model import KnowledgeDocument, KnowledgeVersion, KnowledgeChunk
from app.modules.knowledge.knowledge_schema import RetrievalResponse, RetrievedSource
from app.modules.processing.job_model import Job
from app.modules.processing.workflow_service import StageFailure
from app.modules.semantics.embedding_model import Embedding
from app.modules.semantics.embedding_model_client import model_info, get_encoder
from app.modules.semantics.embeddings_service import cosine

MINIMUM_SIMILARITY = .30


def preview(database,settings,body):
    with database.sessions() as session:
        agency_id = require_workspace(session).id
        query = body.query_text
        if body.lead_id:
            from app.modules.leads.leads_service import require_lead
            lead = require_lead(session,str(body.lead_id))
            if not query:
                query = lead.description
                if not query: raise AppError('COMPANY_CONTEXT_REQUIRED','Add a company description or enter its needs for this preview.',422)
        if body.service_id:
            service = session.scalar(select(Service).where(Service.id==str(body.service_id),Service.agency_id==agency_id,Service.active.is_(True)))
            if service is None: raise AppError('SERVICE_NOT_FOUND','Choose an active service from your agency.',404)
            query = f'{query}\nRelevant service: {service.name}. {service.description or ""}'
    info = model_info(settings)
    if info['status']!='available': raise AppError('EMBEDDING_UNAVAILABLE','The local embedding model is unavailable. Knowledge remains saved.',503)
    identity = info['identity']; space = snapshot_hash(identity)
    try:
        encoder = get_encoder(SimpleNamespace(settings=settings),identity)
        selection = encoder.select(query)
        if selection['truncated']: raise AppError('KNOWLEDGE_QUERY_TOO_LONG','Shorten the query to fit the local model (254 text tokens).',422)
        query_vector = encoder.encode(selection,lambda:None)
        if model_info(settings)!=info: raise AppError('EMBEDDING_UNAVAILABLE','The embedding model changed. Retry the preview.',503)
        with database.sessions() as session:
            newer = aliased(Job)
            newer_completed = select(newer.id).where(newer.agency_id==Job.agency_id,newer.scope==Job.scope,
                newer.kind=='knowledge_index',newer.status=='completed',
                newer.input_snapshot['document_revision'].as_integer()==KnowledgeDocument.revision,
                or_(newer.queued_at>Job.queued_at,and_(newer.queued_at==Job.queued_at,newer.id>Job.id))).exists()
            statement = (select(KnowledgeChunk,KnowledgeVersion,KnowledgeDocument,Embedding,Job)
                .join(KnowledgeVersion,KnowledgeChunk.version_id==KnowledgeVersion.id)
                .join(KnowledgeDocument,KnowledgeVersion.document_id==KnowledgeDocument.id)
                .join(Embedding,KnowledgeChunk.embedding_id==Embedding.id)
                .join(Job,KnowledgeChunk.job_id==Job.id)
                .where(KnowledgeDocument.agency_id==agency_id,Embedding.agency_id==agency_id,Job.agency_id==agency_id,
                       KnowledgeDocument.current_version_id==KnowledgeVersion.id,KnowledgeDocument.active.is_(True),
                       KnowledgeDocument.approved.is_(True),Job.status=='completed',Job.kind=='knowledge_index',
                       Job.input_snapshot['document_revision'].as_integer()==KnowledgeDocument.revision,~newer_completed))
            if not body.include_demo: statement=statement.where(KnowledgeVersion.demo.is_(False))
            scored=[]; incompatible=0; candidates=0
            for chunk,version,document,embedding,job in session.execute(statement).yield_per(100):
                if job.input_snapshot['document_revision']!=document.revision: continue
                if embedding.space_hash!=space or embedding.metadata_json.get('model')!=identity or chunk.settings.get('version')!='agency-chunks-v1':
                    incompatible+=1; continue
                candidates+=1
                raw,_ = cosine(query_vector,np.frombuffer(embedding.vector,dtype='<f4'),space,embedding.space_hash)
                if raw<MINIMUM_SIMILARITY: continue
                source=RetrievedSource(chunk_id=chunk.id,document_id=document.id,version_id=version.id,version=version.version,
                    title=version.title,document_type=version.document_type,demo=version.demo,text=chunk.text,
                    start_offset=chunk.start_offset,end_offset=chunk.end_offset,similarity=round(raw,6))
                scored.append(source)
                scored.sort(key=lambda item:(-item.similarity,item.chunk_id))
                scored=scored[:3]
        return RetrievalResponse(query_text=query,sources=scored,empty_reason=None if scored else ('NO_RELEVANT_SOURCES' if candidates else 'NO_ELIGIBLE_INDEXED_KNOWLEDGE'),
            minimum_similarity=MINIMUM_SIMILARITY,candidate_count=candidates,excluded_incompatible=incompatible,model=identity)
    except StageFailure as exc:
        raise AppError(exc.code,'The embedding or retrieval step could not complete. Knowledge remains saved.',503) from None
