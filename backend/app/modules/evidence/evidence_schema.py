from datetime import datetime, timezone
from typing import Literal
from pydantic import Field, StrictBool, field_validator, model_validator
from app.modules.foundation.common_schema import StrictModel
from app.modules.foundation.urls import normalize_website


class SavedEvidenceMetadata(StrictModel):
    source_mode: Literal['uploaded', 'cached'] = 'uploaded'
    original_url: str | None = Field(default=None, max_length=2048)
    collected_at: datetime | None = None
    title: str | None = Field(default=None, max_length=200)

    @field_validator('original_url')
    @classmethod
    def public_url(cls, value):
        return normalize_website(value).normalized_url if value else None

    @field_validator('collected_at')
    @classmethod
    def collection_time(cls, value):
        if value is not None:
            if value.tzinfo is None or value > datetime.now(timezone.utc):
                raise ValueError('Use a past timestamp with a timezone.')
            return value.astimezone(timezone.utc)
        return value


class SavedEvidenceReceipt(StrictModel):
    upload_token: str
    source_mode: Literal['uploaded', 'cached']
    imported_at: str
    expires_at: str
    text_available: bool
    image_available: bool
    warnings: list[str]


class EvidenceResponse(StrictModel):
    id: str
    run_id: str
    kind: Literal['text', 'image']
    source_mode: Literal['uploaded', 'cached', 'live']
    source_label: str
    original_url: str | None
    collected_at: str | None
    imported_at: str
    metadata: dict
    usable: bool
    review_reason: str | None
    revision: int
    updated_at: str
    image_url: str | None = None
    thumbnail_url: str | None = None


class EvidenceList(StrictModel):
    items: list[EvidenceResponse]
    page: int = 1
    page_size: int = 25
    total: int


class EvidenceReview(StrictModel):
    usable: StrictBool
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def unusable_reason(self):
        self.reason = self.reason.strip() if self.reason else None
        if not self.usable and (not self.reason or len(self.reason) < 3):
            raise ValueError('Explain why this evidence is unusable.')
        return self
