from uuid import UUID
from typing import Literal
from pydantic import Field, model_validator, ConfigDict
from app.modules.foundation.common_schema import StrictModel


class ScoreResponse(StrictModel):
    id: str
    run_id: str
    lead_id: str
    created_at: str
    score: float | None
    coverage: float
    score_band: str | None
    priority: str
    ineligible: bool
    exclusion_reasons: list[dict]
    recommended_for_qualification: bool
    is_current: bool
    stale_reasons: list[str]
    components: list[dict]
    thresholds: dict
    eligible_weight: float
    available_weight: float
    numerator: float
    provenance: dict
    overrides: list[dict] = Field(default_factory=list)
    reviewer_priority: str | None = None
    exclusion_override: bool = False
    qualification_override: bool = False


class ScoreList(StrictModel):
    items: list[ScoreResponse]
    page: int
    page_size: int
    total: int


class OverrideCreate(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    score_id: UUID
    kind: Literal['priority', 'exclusion', 'qualification']
    value: str
    reason: str = Field(min_length=3, max_length=1000)
    reviewer: str = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def allowed_value(self):
        allowed = ['High', 'Medium', 'Low', 'Needs review', 'clear'] if self.kind == 'priority' else ['allow', 'clear']
        if self.value not in allowed: raise ValueError('Choose a valid value for the override kind.')
        return self
