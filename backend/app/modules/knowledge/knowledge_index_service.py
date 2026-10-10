"""Prepare an index privately; publish all passages together when its stage commits."""
from app.modules.foundation.hashing import snapshot_hash
from app.modules.knowledge.knowledge_model import KnowledgeDocument, KnowledgeVersion, KnowledgeChunk
from app.modules.knowledge.knowledge_service import eligible_job
from app.modules.processing.job_model import Job
from app.modules.processing.workflow_service import StageResult, StageFailure
from app.modules.semantics.embedding_model_client import get_encoder, model_info
from app.modules.semantics.embeddings_service import vector_for


def index_knowledge(context, snapshot, previous_outputs):
    from app.modules.knowledge.chunking_service import split_text, CHUNK_SETTINGS
    context.checkpoint()
    with context.worker.database.sessions() as session:
        job = session.get(Job,context.job_id)
        if not eligible_job(session,job): raise StageFailure('KNOWLEDGE_VERSION_CHANGED')
        version = session.get(KnowledgeVersion,snapshot['version_id'])
        text,agency_id = version.text,job.agency_id
    identity = snapshot['models']['embedding']['identity']
    encoder = get_encoder(context.worker,identity)
    passages = split_text(text,encoder.tokenizer,context.checkpoint)
    prepared = []
    for ordinal,passage in enumerate(passages):
        context.checkpoint()
        embedding_id,vector,selection,cached = vector_for(context,encoder,agency_id,'knowledge',passage['text'])
        if selection['truncated']: raise StageFailure('KNOWLEDGE_CHUNK_INVALID')
        prepared.append({**passage,'embedding_id':embedding_id,'ordinal':ordinal,'settings':CHUNK_SETTINGS})
    if model_info(context.worker.settings) != {'status':'available','identity':identity}:
        raise StageFailure('EMBEDDING_UNAVAILABLE')
    context.checkpoint()
    context.worker._knowledge_index_batch = (context.job_id,prepared)
    return StageResult(usable=True,output={'document_id':snapshot['document_id'],'version_id':snapshot['version_id'],
                                         'chunk_count':len(prepared),'settings':CHUNK_SETTINGS,'space_hash':snapshot_hash(identity)})


def persist_index(session,job,result,batch):
    if job.cancel_requested: raise StageFailure('JOB_CANCELLED')
    if not eligible_job(session,job): raise StageFailure('KNOWLEDGE_VERSION_CHANGED')
    if not batch or batch[0]!=job.id or len(batch[1])!=result.output['chunk_count']:
        raise StageFailure('KNOWLEDGE_CHUNK_INVALID')
    for values in batch[1]:
        session.add(KnowledgeChunk(version_id=job.input_snapshot['version_id'],job_id=job.id,**values))
