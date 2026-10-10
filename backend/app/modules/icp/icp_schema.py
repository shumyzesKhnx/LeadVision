"""Customer-profile contracts; nested settings replace their entire object on PATCH."""

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from app.modules.foundation.common_schema import StrictModel
from app.modules.icp.scoring_config_schema import Criteria, Exclusions, Thresholds, Weights

CREATE_EXAMPLE = {
    'name': 'UK software companies',
    'target_text': 'UK software companies with 20 to 100 employees that need a better website.',
    'criteria': {'industries': ['software'], 'countries': ['GB'], 'employee_min': 20, 'employee_max': 100},
    'desired_needs': ['Website redesign'],
}


class AnalyticalConfig(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    target_text: str = Field(default='', max_length=10000)
    criteria: Criteria = Field(default_factory=Criteria)
    exclusions: Exclusions = Field(default_factory=Exclusions)
    desired_needs: list[str] = Field(default_factory=list, max_length=50)
    preferences_text: str = Field(default='', max_length=5000)
    weights: Weights = Field(default_factory=Weights)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    visual_calibration_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator('desired_needs')
    @classmethod
    def normalized_needs(cls, values):
        values = [value.strip() for value in values]
        if any(not value or len(value) > 200 for value in values):
            raise ValueError('Each desired need must contain 1 to 200 characters.')
        return sorted(set(values))


class ICPCreate(AnalyticalConfig):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True,
                             json_schema_extra={'examples': [CREATE_EXAMPLE]})
    name: str = Field(min_length=1, max_length=200)


class ICPPatch(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    archived: StrictBool | None = None
    target_text: str | None = Field(default=None, max_length=10000)
    criteria: Criteria | None = None
    exclusions: Exclusions | None = None
    desired_needs: list[str] | None = Field(default=None, max_length=50)
    preferences_text: str | None = Field(default=None, max_length=5000)
    weights: Weights | None = None
    thresholds: Thresholds | None = None
    visual_calibration_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator('desired_needs')
    @classmethod
    def normalized_needs(cls, values):
        if values is None:
            return None
        return AnalyticalConfig.normalized_needs(values)

    @model_validator(mode='after')
    def valid_patch(self):
        if not self.model_fields_set:
            raise ValueError('Supply at least one field to edit.')
        if any(getattr(self, key) is None for key in self.model_fields_set - {'visual_calibration_id'}):
            raise ValueError('Required profile fields cannot be null; use empty lists/text to clear them.')
        return self


class ICPVersionResponse(StrictModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    id: str
    icp_id: str
    version: int
    config: AnalyticalConfig
    score_rule_version: str
    content_hash: str
    semantic_input_hash: str
    created_at: str


class InvalidationResponse(StrictModel):
    scores_changed: bool = False
    semantic_changed: bool = False
    affected_campaigns: int = 0
    affected_results: int = 0


class ICPResponse(StrictModel):
    id: str
    agency_id: str
    name: str
    archived: bool
    revision: int
    created_at: str
    updated_at: str
    current_version: ICPVersionResponse
    eligible_components: list[str]
    resolved_countries: list[str]
    invalidation: InvalidationResponse = Field(default_factory=InvalidationResponse)


class ICPList(StrictModel):
    items: list[ICPResponse]
    page: int
    page_size: int
    total: int


class ICPVersionList(StrictModel):
    items: list[ICPVersionResponse]
    page: int
    page_size: int
    total: int
