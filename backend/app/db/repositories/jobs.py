from sqlalchemy import func, select
from app.models.job import Job, JobStage
from app.models.analysis_run import AnalysisRun


def active_job(session, lead_id):
    return session.scalar(select(Job).where(Job.lead_id == lead_id, Job.status.in_(['queued', 'running'])))


def latest_job(session, lead_id):
    return session.scalar(select(Job).where(Job.lead_id == lead_id)
                          .order_by(Job.queued_at.desc(), Job.id.desc()).limit(1))


def replay(session, agency_id, scope, key):
    return session.scalar(select(Job).where(Job.agency_id == agency_id, Job.scope == scope, Job.idempotency_key == key))


def get_job(session, job_id, agency_id):
    return session.scalar(select(Job).where(Job.id == job_id, Job.agency_id == agency_id))


def stages(session, job_id):
    return list(session.scalars(select(JobStage).where(JobStage.job_id == job_id).order_by(JobStage.ordinal)))


def run_for_job(session, job_id):
    return session.execute(select(AnalysisRun).where(AnalysisRun.job_id == job_id)).scalar_one()


def run_history(session, lead_id, page, page_size):
    count = session.scalar(select(func.count()).select_from(AnalysisRun).where(AnalysisRun.lead_id == lead_id))
    items = list(session.scalars(select(AnalysisRun).where(AnalysisRun.lead_id == lead_id)
                                .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
                                .offset((page - 1) * page_size).limit(page_size)))
    return items, count
