"""Bounded inputs and explicit source responses."""
from typing import Literal
from uuid import UUID
from pydantic import Field, StrictBool, field_validator, model_validator
from app.modules.foundation.common_schema import StrictModel

DocumentType = Literal['service', 'case_study', 'experience', 'other']
MAX_TEXT_BYTES = 1_000_000


def clean_text(value):
    value = value.strip()
    if not value or '\x00' in value:
        raise ValueError('Provide readable text without null characters.')
    if len(value.encode('utf-8')) > MAX_TEXT_BYTES:
        from app.modules.foundation.errors import AppError
        raise AppError('KNOWLEDGE_TOO_LARGE', 'Knowledge text must be at most 1 MB.', 413)
    return value


class KnowledgeCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    document_type: DocumentType = 'other'
    text: str = Field(min_length=1, max_length=MAX_TEXT_BYTES)
    demo: StrictBool = False
    approved: StrictBool = False
    _clean_text = field_validator('text')(clean_text)

    @field_validator('title')
    @classmethod
    def title_present(cls, value):
        if not value.strip(): raise ValueError('Provide a title.')
        return value.strip()


class KnowledgePatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    document_type: DocumentType | None = None
    text: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT_BYTES)
    demo: StrictBool | None = None
    approved: StrictBool | None = None
    active: StrictBool | None = None

    @model_validator(mode='after')
    def valid_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('Provide at least one non-null change.')
        if self.text is not None: self.text = clean_text(self.text)
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title: raise ValueError('Provide a title.')
        return self


class KnowledgeVersionResponse(StrictModel):
    id: str
    version: int
    title: str
    document_type: DocumentType
    demo: bool
    content_hash: str
    created_at: str
    text: str | None = None


class KnowledgeResponse(StrictModel):
    id: str
    agency_id: str
    revision: int
    active: bool
    approved: bool
    created_at: str
    updated_at: str
    current_version: KnowledgeVersionResponse
    index_status: str
    index_job_id: str | None
    chunk_count: int
    versions: list[KnowledgeVersionResponse] = Field(default_factory=list)


class KnowledgePage(StrictModel):
    items: list[KnowledgeResponse]
    page: int
    page_size: int
    total: int


class IndexRequest(StrictModel):
    version_id: UUID


class IndexReceipt(StrictModel):
    job_id: str
    status: str
    poll_url: str
    document_id: str
    version_id: str


class RetrievalPreview(StrictModel):
    query_text: str | None = Field(default=None, min_length=3, max_length=4000)
    lead_id: UUID | None = None
    service_id: UUID | None = None
    include_demo: StrictBool = False

    @model_validator(mode='after')
    def has_context(self):
        if self.query_text is not None:
            self.query_text = self.query_text.strip()
            if len(self.query_text) < 3: raise ValueError('Describe the company or its needs.')
        if not self.query_text and not self.lead_id:
            raise ValueError('Provide query_text or a lead_id with a saved description.')
        return self


class RetrievedSource(StrictModel):
    chunk_id: str
    document_id: str
    version_id: str
    version: int
    title: str
    document_type: DocumentType
    demo: bool
    text: str
    start_offset: int
    end_offset: int
    similarity: float


class RetrievalResponse(StrictModel):
    query_text: str
    sources: list[RetrievedSource]
    empty_reason: str | None
    minimum_similarity: float
    candidate_count: int
    excluded_incompatible: int
    model: dict
