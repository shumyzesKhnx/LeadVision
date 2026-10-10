"""LangChain splitting measured with the same tokenizer used for embeddings."""
from importlib.metadata import version
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.modules.processing.workflow_service import StageFailure

CHUNK_SETTINGS = {'version':'agency-chunks-v1','max_tokens':180,'overlap_tokens':30,
                  'splitter':'RecursiveCharacterTextSplitter','library_version':version('langchain-text-splitters')}


def split_text(text, tokenizer, checkpoint=lambda: None):
    count = lambda value: len(tokenizer.encode(value, add_special_tokens=False).ids)
    splitter = RecursiveCharacterTextSplitter(chunk_size=180, chunk_overlap=30,
        length_function=count, separators=['\n\n','\n','. ',' ',''], strip_whitespace=True)
    result = []
    previous_start = 0
    previous_end = 0
    for passage in splitter.split_text(text):
        checkpoint()
        # LangChain's character-based start-index heuristic does not match token overlap.
        # Search after the last start, allowing only the configured overlap at its end.
        if result:
            offsets = tokenizer.encode(text[previous_start:previous_end],add_special_tokens=False).offsets
            search_start = previous_start + (offsets[max(0,len(offsets)-30)][0] if offsets else 1)
            search_start = max(previous_start+1, search_start)
        else: search_start = 0
        start = text.find(passage, search_start)
        if start < 0: raise StageFailure('KNOWLEDGE_CHUNK_INVALID')
        tokens = count(passage)
        # Do not silently truncate a passage or produce an incomplete index.
        if not 1 <= tokens <= 180 or len(passage) > 12000:
            raise StageFailure('KNOWLEDGE_CHUNK_INVALID')
        result.append({'text':passage,'start_offset':start,'end_offset':start+len(passage),'token_count':tokens})
        previous_start,previous_end = start,start+len(passage)
        if len(result)>1000: raise StageFailure('KNOWLEDGE_CHUNK_LIMIT')
    if not result: raise StageFailure('EMPTY_TEXT')
    return result
