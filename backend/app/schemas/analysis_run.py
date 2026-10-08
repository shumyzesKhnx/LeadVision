from app.schemas.common import StrictModel
from app.schemas.job import JobResponse


class AnalysisRunResponse(StrictModel):
    id: str
    lead_id: str
    job_id: str
    icp_version_id: str
    lead_input_revision: int
    evidence_mode: str
    fingerprint: str
    created_at: str
    input_snapshot: dict
    is_current: bool
    stale_reasons: list[str]
    job: JobResponse
    business_analysis: dict | None = None


class AnalysisRunList(StrictModel):
    items: list[AnalysisRunResponse]
    page: int
    page_size: int
    total: int
