from typing import Literal
from pydantic import Field, StrictInt
from app.modules.foundation.common_schema import StrictModel


class Citation(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=500)


class CitedValue(Citation):
    value: str = Field(min_length=1, max_length=200)


class EmployeeFact(Citation):
    value: StrictInt = Field(ge=0, le=100_000_000)


class Opportunity(StrictModel):
    description: str = Field(min_length=1, max_length=300)
    observation_ids: list[str] = Field(min_length=1, max_length=10)
    hypothesis: Literal[True]


class BusinessOutput(StrictModel):
    summary: str = Field(min_length=1, max_length=1000)
    summary_sources: list[Citation] = Field(min_length=1, max_length=10)
    industry: CitedValue | None
    products: list[CitedValue] = Field(max_length=10)
    markets: list[CitedValue] = Field(max_length=10)
    employee_count: EmployeeFact | None
    opportunities: list[Opportunity] = Field(max_length=10)
