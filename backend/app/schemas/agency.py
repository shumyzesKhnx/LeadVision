"""Agency forms and responses; optional contacts are explicitly user-provided."""

import re

from pydantic import ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.schemas.common import StrictModel


class ContactDetails(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=100)
    website: HttpUrl | None = None

    @field_validator("email")
    @classmethod
    def email_has_basic_business_syntax(cls, value):
        if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a business email address.")
        return value

    @field_validator("website")
    @classmethod
    def website_has_no_credentials(cls, value):
        if value is not None and (value.username or value.password):
            raise ValueError("Business website URLs cannot contain credentials.")
        return value


class AgencyCreate(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200, examples=["TechNova"])
    description: str | None = Field(default=None, max_length=5000)
    contact: ContactDetails | None = None


class AgencyPatch(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    contact: ContactDetails | None = None

    @field_validator("name", mode="before")
    @classmethod
    def supplied_name_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Agency name cannot be cleared.")
        return value

    @model_validator(mode="after")
    def has_a_change(self):
        if not self.model_fields_set:
            raise ValueError("Supply at least one field to edit.")
        return self


class AgencyResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: str
    name: str
    description: str | None
    contact: ContactDetails | None
    revision: int
    active_service_count: int = 0
    created_at: str
    updated_at: str
