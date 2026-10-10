"""Services require an offer description; removal means active=false."""

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from app.modules.foundation.common_schema import StrictModel


class ServiceCreate(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200, examples=["Website redesign"])
    description: str = Field(min_length=1, max_length=5000, examples=["We redesign business websites."])


class ServicePatch(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    active: StrictBool | None = None

    @field_validator("name", "description", "active", mode="before")
    @classmethod
    def supplied_fields_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Required service fields cannot be cleared.")
        return value

    @model_validator(mode="after")
    def has_a_change(self):
        if not self.model_fields_set:
            raise ValueError("Supply at least one field to edit.")
        return self


class ServiceResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: str
    agency_id: str
    name: str
    description: str
    active: bool
    revision: int
    created_at: str
    updated_at: str


class ServiceList(StrictModel):
    items: list[ServiceResponse]
    page: int
    page_size: int
    total: int
