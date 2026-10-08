from sqlalchemy import select
from app.core.clock import utc_now
from app.models.job import Job
from app.models.maintenance import WorkerState
from app.services.jobs import stale_reasons
from app.db.repositories.jobs import run_for_job
from app.services.workflow import public_error
from app.worker.recovery import terminate


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
        if stale_reasons(session, run_for_job(session, job.id)):
            terminate(session, job, 'failed', public_error('INPUT_CHANGED', retryable=True))
            return None
        job.status = 'running'
        job.owner_token = owner
        job.started_at = utc_now()
        return job.id
