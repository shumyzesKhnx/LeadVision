from typing import Literal
from pydantic import Field, StrictBool
from app.modules.foundation.common_schema import StrictModel

JobStatus = Literal['queued', 'running', 'completed', 'partial', 'failed', 'cancelled']


class AnalysisJobCreate(StrictModel):
    mode: Literal['live', 'cached', 'uploaded'] = 'live'
    upload_token: str | None = Field(default=None, min_length=1, max_length=128)
    include_supporting_pages: StrictBool = False


class JobRetry(StrictModel):
    upload_token: str | None = Field(default=None, min_length=1, max_length=128)


class JobReceipt(StrictModel):
    job_id: str
    status: JobStatus
    poll_url: str
    run_id: str | None


class StageError(StrictModel):
    code: str = Field(max_length=100)
    message: str = Field(max_length=200)
    stage: str | None = None
    retryable: bool = False


class StageResponse(StrictModel):
    name: str
    state: str
    attempts: int
    usable: bool
    output: dict | None
    warnings: list[str]
    error: StageError | None
    started_at: str | None
    finished_at: str | None


class JobProgress(StrictModel):
    finished_stages: int
    total_stages: int


class JobResult(StrictModel):
    run_id: str | None
    draft_id: str | None = None


class JobResponse(StrictModel):
    id: str
    lead_id: str | None
    kind: str
    status: JobStatus
    current_stage: str | None
    progress: JobProgress
    queued_at: str
    started_at: str | None
    finished_at: str | None
    cancel_requested: bool
    retry_of_id: str | None
    warnings: list[str]
    errors: list[StageError]
    stages: list[StageResponse]
    result: JobResult
    retryable: bool
