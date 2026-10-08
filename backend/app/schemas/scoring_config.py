"""Bounded structured criteria and scoring settings, without scoring a lead yet."""

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from app.core.errors import AppError
from app.schemas.common import StrictModel, ErrorDetail
from app.services.criteria import country_code, industry_label, region_key


class SizeBounds(StrictModel):
    employee_min: StrictInt | None = Field(default=None, ge=0, le=2_147_483_647)
    employee_max: StrictInt | None = Field(default=None, ge=0, le=2_147_483_647)

    @model_validator(mode='after')
    def valid_range(self):
        if self.employee_min is not None and self.employee_max is not None and self.employee_min > self.employee_max:
            raise AppError('INVALID_SIZE_RANGE', 'Minimum employees cannot exceed maximum employees.', 422,
                           [ErrorDetail(field='employee_min', reason='Must be at most employee_max.')])
        return self


class Exclusions(SizeBounds):
    industries: list[str] = Field(default_factory=list, max_length=100)
    countries: list[str] = Field(default_factory=list, max_length=249)

    @field_validator('industries')
    @classmethod
    def normalize_industries(cls, values):
        normalized = [industry_label(value) for value in values]
        if any(not value or len(value) > 100 for value in normalized):
            raise ValueError('Industry labels must contain 1 to 100 characters.')
        return sorted(set(normalized))

    @field_validator('countries')
    @classmethod
    def normalize_countries(cls, values):
        return sorted({country_code(value) for value in values})


class Criteria(Exclusions):
    regions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('regions')
    @classmethod
    def normalize_regions(cls, values):
        return sorted({region_key(value) for value in values})


class Weights(StrictModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    industry: float = Field(default=25, ge=0, le=10000)
    geography: float = Field(default=20, ge=0, le=10000)
    size: float = Field(default=15, ge=0, le=10000)
    semantic: float = Field(default=40, ge=0, le=10000)
    visual: float = Field(default=0, ge=0, le=10000)

    @field_validator('industry', 'geography', 'size', 'semantic', 'visual', mode='before')
    @classmethod
    def numeric_only(cls, value):
        if type(value) not in (int, float):
            raise ValueError('Enter a finite nonnegative number.')
        return value


class Thresholds(StrictModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    high: float = Field(default=75, ge=0, le=100)
    medium: float = Field(default=50, ge=0, le=100)
    minimum_coverage: float = Field(default=0.6, ge=0, le=1)

    @field_validator('high', 'medium', 'minimum_coverage', mode='before')
    @classmethod
    def numeric_only(cls, value):
        if type(value) not in (int, float):
            raise ValueError('Enter a finite number.')
        return value

    @model_validator(mode='after')
    def valid_bands(self):
        if self.medium >= self.high:
            raise AppError('INVALID_THRESHOLDS', 'Medium must be below High.', 422,
                           [ErrorDetail(field='thresholds.medium', reason='Must be below thresholds.high.')])
        return self
