from typing import Literal
from uuid import UUID
from pydantic import Field, StrictBool
from app.modules.foundation.common_schema import StrictModel


class OutreachCreate(StrictModel):
    service_id: UUID
    analysis_run_id: UUID | None = None
    acknowledge_missing_analysis: StrictBool = False


class Claim(StrictModel):
    text: str = Field(min_length=3, max_length=500)
    source_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=3, max_length=500)


class DraftText(StrictModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=2000)
    claims: list[Claim] = Field(default_factory=list, max_length=12)


class DraftReview(StrictModel):
    decision: Literal['Approved', 'Rejected']
    reviewer: str = Field(min_length=1, max_length=100)
    factual_review_acknowledged: StrictBool = False
    reason: str | None = Field(default=None, min_length=1, max_length=500)


class OutreachReceipt(StrictModel):
    job_id: str
    status: str
    poll_url: str
