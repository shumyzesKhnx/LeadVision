"""Lead inputs preserve missing values and keep corrections separate from analysis."""

import re
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from app.modules.foundation.urls import normalize_website
from app.modules.foundation.common_schema import StrictModel
from app.modules.icp.criteria_service import country_code, industry_label

PipelineState = Literal['New', 'Reviewed', 'Qualified', 'Contacted', 'Replied', 'Converted', 'Lost']
Priority = Literal['High', 'Medium', 'Low', 'Needs review']


class LeadFields(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    company_name: str = Field(min_length=1, max_length=200, examples=['Demo Software Company'])
    website: str = Field(min_length=1, max_length=2048, examples=['https://example.com'])
    industry: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=2)
    employee_count: StrictInt | None = Field(default=None, ge=0, le=2_147_483_647)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=254)
    description: str | None = Field(default=None, max_length=10000)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator('website')
    @classmethod
    def valid_website(cls, value):
        normalize_website(value)
        return value

    @field_validator('industry', 'country', 'contact_name', 'contact_email', 'description', 'notes')
    @classmethod
    def optional_text(cls, value, info):
        if value is None or not value.strip():
            return None
        if info.field_name == 'industry':
            return industry_label(value)
        if info.field_name == 'country':
            return country_code(value)
        if info.field_name == 'contact_email' and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
            raise ValueError('Enter a valid email address.')
        return value


class LeadCreate(LeadFields):
    campaign_id: UUID


class LeadPatch(LeadFields):
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, min_length=1, max_length=2048)
    correction_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator('company_name', 'website', mode='before')
    @classmethod
    def required_fields_cannot_be_null(cls, value):
        if value is None:
            raise ValueError('Company name and website cannot be cleared.')
        return value

    @model_validator(mode='after')
    def has_changes(self):
        if not self.model_fields_set - {'correction_reason'}:
            raise ValueError('Supply at least one field to edit.')
        return self


class LeadResponse(StrictModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: str
    campaign_id: str
    company_id: str
    company_name: str
    website: str
    normalized_url: str
    normalized_domain: str
    industry: str | None
    country: str | None
    employee_count: int | None
    contact_name: str | None
    contact_email: str | None
    description: str | None
    notes: str | None
    pipeline_state: PipelineState
    revision: int
    analytical_input_revision: int
    created_at: str
    updated_at: str
    score: float | None = None
    score_id: str | None = None
    coverage: float = 0
    score_band: str | None = None
    is_current: bool = False
    ineligible: bool = False
    recommended_for_qualification: bool = False
    reviewer_priority: str | None = None
    priority: Priority = 'Needs review'
    processing_status: str = 'not_started'
    latest_job_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class LeadFactResponse(StrictModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: str
    lead_id: str
    field_name: str
    value: str | int | None
    source_category: str
    verified: bool
    actor_label: str | None
    revision: int
    supersedes_fact_id: str | None
    correction_reason: str | None
    recorded_at: str


class LeadActivityResponse(StrictModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: str
    action: str
    origin: str
    created_at: str


class LeadInvalidation(StrictModel):
    analytical_inputs_changed: bool = False
    changed_fields: list[str] = Field(default_factory=list)
    affected_results: int = 0


class LeadDetail(LeadResponse):
    provenance: list[LeadFactResponse] = Field(default_factory=list)
    activities: list[LeadActivityResponse] = Field(default_factory=list)
    activities_total: int = 0
    evidence: list[dict] = Field(default_factory=list)
    business_analysis: dict | None = None
    visual_analysis: dict | None = None
    semantic_result: dict | None = None
    score_components: list[dict] = Field(default_factory=list)
    score_detail: dict | None = None
    drafts: list[dict] = Field(default_factory=list)
    invalidation: LeadInvalidation = Field(default_factory=LeadInvalidation)


class LeadList(StrictModel):
    items: list[LeadResponse]
    page: int
    page_size: int
    total: int


class LeadFactList(StrictModel):
    items: list[LeadFactResponse]
    page: int
    page_size: int
    total: int
