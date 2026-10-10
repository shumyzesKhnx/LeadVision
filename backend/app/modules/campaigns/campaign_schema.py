"""Campaign input validation and current targeting/readiness summaries."""

from uuid import UUID

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from app.modules.foundation.common_schema import StrictModel


class CampaignCreate(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200, examples=['Pakistan website prospects'])
    icp_id: UUID = Field(description='Copy the top-level id from GET /api/v1/icps. Remove quotation marks.')
    description: str | None = Field(default=None, max_length=5000)


class CampaignPatch(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    icp_id: UUID | None = None
    description: str | None = Field(default=None, max_length=5000)
    archived: StrictBool | None = None

    @field_validator('name', 'icp_id', 'archived', mode='before')
    @classmethod
    def required_fields_cannot_be_null(cls, value):
        if value is None:
            raise ValueError('This field cannot be cleared.')
        return value

    @model_validator(mode='after')
    def has_changes(self):
        if not self.model_fields_set:
            raise ValueError('Supply at least one field to edit.')
        return self


class CampaignInvalidation(StrictModel):
    targeting_changed: bool = False
    affected_leads: int = 0


class CampaignResponse(StrictModel):
    id: str
    agency_id: str
    icp_id: str
    name: str
    description: str | None
    archived: bool
    revision: int
    created_at: str
    updated_at: str
    icp_name: str
    current_icp_version_id: str
    current_icp_version: int
    analysis_allowed: bool
    analysis_blocked_reason: str | None
    lead_count: int = 0
    invalidation: CampaignInvalidation = Field(default_factory=CampaignInvalidation)


class CampaignList(StrictModel):
    items: list[CampaignResponse]
    page: int
    page_size: int
    total: int
