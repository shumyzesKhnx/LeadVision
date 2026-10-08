from typing import Literal
from pydantic import Field
from app.schemas.common import StrictModel, ErrorDetail


class ImportRow(StrictModel):
    row: int
    status: Literal['accepted', 'duplicate', 'invalid', 'not_processed']
    lead_id: str | None = None
    errors: list[ErrorDetail] = Field(default_factory=list, max_length=10)
    warnings: list[str] = Field(default_factory=list)


class ImportReport(StrictModel):
    items: list[ImportRow] = Field(default_factory=list, max_length=100)
    accepted: int = 0
    duplicate: int = 0
    invalid: int = 0
    not_processed: int = 0
    warnings: list[str] = Field(default_factory=list)
