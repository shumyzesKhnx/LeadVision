"""Only the OS-lock owner may recover abandoned running jobs."""
from sqlalchemy import select
from app.modules.foundation.clock import utc_now
from app.modules.processing.job_model import Job
from app.modules.processing import jobs_repository as repository
from app.modules.processing.activity_service import record_activity
from app.modules.processing.workflow_service import public_error


def terminate(session, job, status, error=None):
    job.status = status
    job.error = error
    job.finished_at = utc_now()
    job.current_stage = None
    for stage in repository.stages(session, job.id):
        if stage.state in {'pending', 'running'}:
            if stage.state == 'running' and error:
                stage.state = 'failed'
                stage.error = {**error, 'stage': stage.name}
            else:
                stage.state = 'skipped'
            stage.finished_at = job.finished_at
    record_activity(session, action=f'{job.kind}.{status}', origin='worker', agency_id=job.agency_id,
                    campaign_id=job.input_snapshot.get('campaign_id'), lead_id=job.lead_id,
                    event_key=f'job:{job.id}:terminal', new_value={'job_id': job.id, 'status': status,
                                                               'error_code': error['code'] if error else None})


def recover_running(session):
    for job in session.scalars(select(Job).where(Job.status == 'running')):
        terminate(session, job, 'failed', public_error('JOB_INTERRUPTED', job.current_stage, True))
