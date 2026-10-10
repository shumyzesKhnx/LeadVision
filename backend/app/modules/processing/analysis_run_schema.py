from app.modules.foundation.common_schema import StrictModel
from app.modules.processing.job_schema import JobResponse


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
    visual_analysis: dict | None = None
    semantic_result: dict | None = None
    score_result: dict | None = None


class AnalysisRunList(StrictModel):
    items: list[AnalysisRunResponse]
    page: int
    page_size: int
    total: int
