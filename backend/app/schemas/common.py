"""Small reusable, strict API schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(StrictModel):
    field: str | None = Field(default=None, max_length=200)
    reason: str = Field(max_length=200)
    stage: str | None = Field(default=None, max_length=100)
    retryable: bool | None = None


class ErrorBody(StrictModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list, max_length=30)
    request_id: str


class ErrorResponse(StrictModel):
    error: ErrorBody


class DependencyHealth(StrictModel):
    status: Literal["ready", "available", "unavailable", "not_implemented"]
    message: str


class HealthResponse(StrictModel):
    status: Literal["ok", "maintenance"]
    application: str = "Lead Vision"
    version: str
    schema_version: int
    checked_at: str
    maintenance: bool
    database: DependencyHealth
    worker: DependencyHealth
    ollama: DependencyHealth
