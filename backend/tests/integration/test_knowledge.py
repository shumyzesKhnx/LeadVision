"""Agency knowledge safety and the real worker lifecycle, using deterministic test vectors."""
import hashlib
import numpy as np
import pytest
from sqlalchemy import select, func
from tokenizers import Tokenizer, models, pre_tokenizers
from app.modules.processing.worker_main import Worker
from app.modules.knowledge.knowledge_model import KnowledgeVersion, KnowledgeChunk
from app.modules.knowledge.chunking_service import split_text
from app.modules.processing.workflow_service import StageFailure


@pytest.fixture
def agency(client):
    response=client.post('/api/v1/agency',json={'name':'Test Agency'})
    assert response.status_code==201,response.text
    return response.json()


@pytest.fixture
def knowledge_worker(client,application,settings,monkeypatch,agency):
    identity={'model':'test-only-knowledge','revision':'a'*40,'config':{'dimensions':384}}
    info={'status':'available','identity':identity}
    tokenizer=Tokenizer(models.WordLevel({'[UNK]':0},unk_token='[UNK]'))
    tokenizer.pre_tokenizer=pre_tokenizers.WhitespaceSplit()
    hooks={'encode':lambda:None}
    class Encoder:
        def __init__(self): self.identity=identity; self.tokenizer=tokenizer
        def select(self,text):
            return {'input_hash':hashlib.sha256(text.strip().encode()).hexdigest(),'selected_text':text,
                    'input_ids':[0],'token_count':len(tokenizer.encode(text).ids),'truncated':False}
        def encode(self,selection,checkpoint):
            checkpoint();hooks['encode']()
            vector=np.zeros(384,dtype='<f4')
            vector[1 if 'tax' in selection['selected_text'].lower() else 0]=1
            return vector
    for path in ('app.modules.semantics.embedding_model_client.model_info',
                 'app.modules.knowledge.knowledge_api.model_info',
                 'app.modules.knowledge.knowledge_index_service.model_info',
                 'app.modules.knowledge.retrieval_service.model_info'):
        monkeypatch.setattr(path,lambda *_:info)
    for path in ('app.modules.knowledge.knowledge_index_service.get_encoder',
                 'app.modules.knowledge.retrieval_service.get_encoder'):
        monkeypatch.setattr(path,lambda *_:Encoder())
    with Worker(application.state.database,settings) as worker:
        yield worker,hooks,info,tokenizer


def document(client,**changes):
    response=client.post('/api/v1/knowledge',json={'title':'Website experience','document_type':'case_study',
        'text':'We redesigned a software company website and improved its navigation.',**changes})
    assert response.status_code==201,response.text
    return response.json()


def patch(client,row,**changes):
    response=client.patch('/api/v1/knowledge/'+row['id'],json=changes,headers={'If-Match':f'"{row["revision"]}"'})
    assert response.status_code==200,response.text
    return response.json()


def index(client,row,key='index'):
    return client.post('/api/v1/knowledge/'+row['id']+'/index-jobs',json={'version_id':row['current_version']['id']},headers={'Idempotency-Key':key})


def preview(client,**changes):
    response=client.post('/api/v1/knowledge/retrieval-preview',json={'query_text':'A software company needs website redesign.',**changes})
    assert response.status_code==200,response.text
    return response.json()


def test_save_review_index_and_retrieve_sources(client,knowledge_worker):
    worker,*_=knowledge_worker
    row=document(client)
    assert not row['approved'] and row['index_status']=='not_indexed'
    assert index(client,row).status_code==409
    row=patch(client,row,approved=True)
    submitted=index(client,row)
    assert submitted.status_code==202,submitted.text
    assert index(client,row).json()==submitted.json()
    assert not preview(client)['sources']
    assert worker.run_once()
    job=client.get(submitted.json()['poll_url']).json()
    assert job['status']=='completed' and job['kind']=='knowledge_index' and job['lead_id'] is None
    assert job['result']['run_id'] is None
    result=preview(client)
    assert len(result['sources'])==1 and result['sources'][0]['text']==row['current_version']['text']
    assert result['sources'][0]['version_id']==row['current_version']['id']
    detail=client.get('/api/v1/knowledge/'+row['id']).json()
    assert detail['chunk_count']==1 and detail['index_status']=='completed'


def test_edits_archive_and_unapproval_immediately_exclude_old_sources(client,knowledge_worker):
    worker,*_=knowledge_worker
    row=document(client,approved=True);assert index(client,row).status_code==202;worker.run_once()
    assert preview(client)['sources']
    row=patch(client,row,text='Our newer website redesign case study.',approved=True)
    assert row['current_version']['version']==2 and not row['approved'] and len(row['versions'])==2
    assert not preview(client)['sources']
    row=patch(client,row,approved=True);index(client,row,'version-2');worker.run_once()
    assert preview(client)['sources'][0]['version']==2
    row=patch(client,row,active=False);assert not preview(client)['sources']
    row=patch(client,row,active=True);index(client,row,'reactivated');worker.run_once()
    row=patch(client,row,approved=False);assert not preview(client)['sources']


def test_demo_is_explicit_and_irrelevant_sources_are_empty(client,knowledge_worker):
    worker,*_=knowledge_worker
    row=document(client,approved=True,demo=True);index(client,row);worker.run_once()
    assert not preview(client)['sources']
    assert preview(client,include_demo=True)['sources'][0]['demo']
    result=preview(client,query_text='A tax accounting company needs tax filing advice.',include_demo=True)
    assert result['empty_reason']=='NO_RELEVANT_SOURCES' and not result['sources']


def test_index_failure_and_edit_during_processing_publish_no_partial_chunks(client,knowledge_worker,application):
    worker,hooks,*_=knowledge_worker
    row=document(client,approved=True)
    def changed():
        hooks['encode']=lambda:None
        patch(client,row,text='This changed while the worker was indexing.')
    hooks['encode']=changed
    submitted=index(client,row).json();worker.run_once()
    job=client.get(submitted['poll_url']).json()
    assert job['status']=='failed' and job['errors'][0]['code']=='KNOWLEDGE_VERSION_CHANGED'
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeChunk))==0
    assert not preview(client)['sources']


def test_cancellation_retry_and_model_compatibility(client,knowledge_worker):
    worker,hooks,info,_=knowledge_worker
    row=document(client,approved=True)
    first=index(client,row).json()
    assert index(client,row,'other').status_code==409
    cancelled=client.post(first['poll_url']+'/cancel',json={})
    assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    retry=client.post(first['poll_url']+'/retry',json={},headers={'Idempotency-Key':'retry'})
    assert retry.status_code==202,retry.text
    worker.run_once();assert preview(client)['sources']
    info['identity']={**info['identity'],'revision':'b'*40}
    result=preview(client)
    assert not result['sources'] and result['excluded_incompatible']==1


def test_late_cancellation_does_not_publish_chunks(client,knowledge_worker,application):
    worker,hooks,*_=knowledge_worker
    row=document(client,approved=True);submitted=index(client,row).json()
    hooks['encode']=lambda:client.post(submitted['poll_url']+'/cancel',json={})
    worker.run_once()
    assert client.get(submitted['poll_url']).json()['status']=='cancelled'
    with application.state.database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeChunk))==0


def test_top_three_and_unapproved_exclusion(client,knowledge_worker):
    worker,*_=knowledge_worker
    for number in range(5):
        row=document(client,title=f'Website case {number}',text=f'We redesigned website number {number}.',approved=True)
        index(client,row,f'index-{number}');worker.run_once()
    document(client,title='Unapproved website redesign')
    first=preview(client);second=preview(client)
    assert len(first['sources'])==3 and first['candidate_count']==5 and first==second
    assert len({source['chunk_id'] for source in first['sources']})==3


@pytest.mark.parametrize('filename,content,mimetype,status',[
    ('facts.pdf',b'%PDF','application/pdf',415),('facts.txt',b'\xff','text/plain',422),
    ('facts.txt',b'  ','text/plain',422),('facts.txt',b'a'*1_000_001,'text/plain',413),
    ('facts.txt',b'hello\x00world','text/plain',422)],ids=['pdf','invalid-encoding','blank','oversize','null-character'])
def test_upload_validation(client,agency,filename,content,mimetype,status):
    response=client.post('/api/v1/knowledge/uploads',data={'title':'Uploaded facts'},files={'file':(filename,content,mimetype)})
    assert response.status_code==status,response.text


def test_utf8_upload_revisions_and_history_are_immutable(client,agency,application):
    response=client.post('/api/v1/knowledge/uploads',data={'title':'Facts','demo':'true'},files={'file':('facts.txt','Agency in پاکستان'.encode(),'text/plain')})
    assert response.status_code==201,response.text
    row=response.json();assert 'پاکستان' in row['current_version']['text'] and row['current_version']['demo']
    assert client.patch('/api/v1/knowledge/'+row['id'],json={'approved':True}).status_code==428
    patch(client,row,approved=True)
    assert client.patch('/api/v1/knowledge/'+row['id'],json={'approved':False},headers={'If-Match':'"1"'}).status_code==409
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError),application.state.database.transaction() as session:
        session.get(KnowledgeVersion,row['current_version']['id']).text='overwrite'


def test_token_bounded_overlap_offsets_and_complete_coverage(knowledge_worker):
    _,_,_,tokenizer=knowledge_worker
    text=' '.join(f'word{number}' for number in range(700))
    chunks=split_text(text,tokenizer)
    assert len(chunks)>1
    assert chunks[0]['start_offset']==0 and chunks[-1]['end_offset']==len(text)
    for chunk in chunks:
        assert 1<=chunk['token_count']<=180
        assert text[chunk['start_offset']:chunk['end_offset']]==chunk['text']
    for first,second in zip(chunks,chunks[1:]):
        assert second['start_offset']<first['end_offset']


def test_missing_model_preserves_saved_document(client,agency):
    row=document(client,approved=True)
    assert index(client,row).status_code==503
    assert client.get('/api/v1/knowledge/'+row['id']).json()['current_version']['text']


def test_reindex_does_not_duplicate_sources_and_replay_survives_edits(client,knowledge_worker):
    worker,*_=knowledge_worker
    row=document(client,approved=True)
    first=index(client,row).json();worker.run_once()
    assert index(client,row,'reindex').status_code==202;worker.run_once()
    result=preview(client)
    assert len(result['sources'])==1 and result['candidate_count']==1
    patch(client,row,text='Updated facts requiring review.')
    assert index(client,row).json()=={**first,'status':'completed'}
