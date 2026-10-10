from sqlalchemy import select
from app.modules.foundation.clock import utc_now
from app.modules.processing.job_model import Job
from app.modules.foundation.maintenance_model import WorkerState
from app.modules.processing.jobs_service import stale_reasons
from app.modules.processing.jobs_repository import run_for_job
from app.modules.processing.workflow_service import public_error
from app.modules.processing.worker_recovery import terminate


def claim_next(database, owner):
    with database.transaction(immediate=True) as session:
        state = session.get(WorkerState, 1)
        if state.owner_token != owner or state.maintenance_requested:
            return None
        job = session.scalar(select(Job).where(Job.status == 'queued').order_by(Job.queued_at, Job.id).limit(1))
        if job is None:
            return None
        if job.cancel_requested:
            terminate(session, job, 'cancelled', public_error('JOB_CANCELLED'))
            return None
        from app.modules.knowledge.knowledge_service import eligible_job
        if job.kind == 'outreach':
            from app.modules.outreach.outreach_service import grounding_stale
            stale = grounding_stale(session, job.input_snapshot)
        else:
            stale = stale_reasons(session, run_for_job(session, job.id)) if job.kind == 'analysis' else not eligible_job(session, job)
        if stale:
            terminate(session, job, 'failed', public_error('INPUT_CHANGED', retryable=True))
            return None
        job.status = 'running'
        job.owner_token = owner
        job.started_at = utc_now()
        return job.id
