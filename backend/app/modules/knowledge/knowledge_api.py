"""Agency knowledge routes; model inference happens outside database transactions."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy import select, func
from app.modules.foundation.dependencies_api import get_database
from app.modules.foundation.database_session import Database
from app.modules.foundation.errors import AppError
from app.modules.foundation.revisions import expected_revision
from app.modules.agency.agency_service import require_workspace
from app.modules.processing.jobs_service import idempotency_key
from app.modules.semantics.embedding_model_client import model_info
from app.modules.knowledge import knowledge_service as service
from app.modules.knowledge.knowledge_model import KnowledgeDocument
from app.modules.knowledge.knowledge_schema import (KnowledgeCreate,KnowledgePatch,KnowledgeResponse,KnowledgePage,
    IndexRequest,IndexReceipt,RetrievalPreview,RetrievalResponse,MAX_TEXT_BYTES)
from app.modules.knowledge.retrieval_service import preview

router=APIRouter(prefix='/api/v1/knowledge',tags=['Agency knowledge'])
DatabaseDependency=Annotated[Database,Depends(get_database)]


def etag(response,result):
    response.headers['ETag']=f'"{result.revision}"'
    return result


@router.get('',response_model=KnowledgePage)
def list_documents(database:DatabaseDependency,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),include_inactive:bool=False):
    with database.sessions() as session:
        agency=require_workspace(session)
        filters=[KnowledgeDocument.agency_id==agency.id]
        if not include_inactive: filters.append(KnowledgeDocument.active.is_(True))
        total=session.scalar(select(func.count()).select_from(KnowledgeDocument).where(*filters))
        rows=session.scalars(select(KnowledgeDocument).where(*filters).order_by(KnowledgeDocument.created_at.desc(),KnowledgeDocument.id).offset((page-1)*page_size).limit(page_size))
        return KnowledgePage(items=[service.response(session,row) for row in rows],page=page,page_size=page_size,total=total)


@router.post('',response_model=KnowledgeResponse,status_code=201)
def create_document(body:KnowledgeCreate,response:Response,database:DatabaseDependency):
    with database.transaction(immediate=True) as session:
        result=service.create(session,body)
    return etag(response,result)


@router.post('/uploads',response_model=KnowledgeResponse,status_code=201)
async def upload_document(response:Response,database:DatabaseDependency,file:Annotated[UploadFile,File()],
    title:Annotated[str,Form()],document_type:Annotated[str,Form()]='other',demo:Annotated[bool,Form()]=False):
    try:
        if not (file.filename or '').lower().endswith('.txt') or file.content_type not in ('text/plain','application/octet-stream'):
            raise AppError('UNSUPPORTED_KNOWLEDGE_FORMAT','Upload a UTF-8 .txt file. PDF and Word files are not supported yet.',415)
        content=await file.read(MAX_TEXT_BYTES+1)
        if len(content)>MAX_TEXT_BYTES: raise AppError('KNOWLEDGE_TOO_LARGE','Knowledge text must be at most 1 MB.',413)
        try: text=content.decode('utf-8-sig')
        except UnicodeDecodeError: raise AppError('INVALID_KNOWLEDGE_ENCODING','Save the text file using UTF-8 encoding.',422) from None
        # Use the same validation for uploaded and pasted knowledge.
        from pydantic import ValidationError
        try: body=KnowledgeCreate(title=title,document_type=document_type,text=text,demo=demo)
        except ValidationError: raise AppError('INVALID_KNOWLEDGE_TEXT','Check the title, type and non-empty readable text.',422) from None
        with database.transaction(immediate=True) as session:
            result=service.create(session,body)
        return etag(response,result)
    finally:
        await file.close()


@router.post('/retrieval-preview',response_model=RetrievalResponse)
def retrieval_preview(body:RetrievalPreview,request:Request,database:DatabaseDependency):
    return preview(database,request.app.state.settings,body)


@router.get('/{document_id}',response_model=KnowledgeResponse)
def get_document(document_id:UUID,response:Response,database:DatabaseDependency):
    with database.sessions() as session:
        result=service.response(session,service.require_document(session,document_id),detail=True)
    return etag(response,result)


@router.patch('/{document_id}',response_model=KnowledgeResponse)
def patch_document(document_id:UUID,body:KnowledgePatch,response:Response,database:DatabaseDependency,revision:Annotated[int,Depends(expected_revision)]):
    with database.transaction(immediate=True) as session:
        result=service.edit(session,document_id,body,revision)
    return etag(response,result)


@router.post('/{document_id}/index-jobs',response_model=IndexReceipt,status_code=202)
def index_document(document_id:UUID,body:IndexRequest,request:Request,response:Response,database:DatabaseDependency,key:Annotated[str,Depends(idempotency_key)]):
    settings=request.app.state.settings
    info=model_info(settings)
    with database.transaction(immediate=True) as session:
        result=service.submit_index(session,settings,document_id,body.version_id,key,info['identity'] if info['status']=='available' else {})
    response.headers['Location']=result.poll_url
    return result
