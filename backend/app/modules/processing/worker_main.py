"""Single process worker; no transaction spans handler/network/model work."""
import copy
import logging
import os
from threading import Event, Thread
import time
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.modules.foundation.clock import utc_now
from app.modules.foundation.config import Settings
from app.modules.foundation.hashing import snapshot_hash
from app.modules.foundation.storage import ArtifactStorage
from app.modules.foundation.migration_runner import migrate
from app.modules.foundation.database_session import Database
from app.modules.processing import jobs_repository as repository
from app.modules.processing.job_model import Job, JobStage
from app.modules.foundation.maintenance_model import WorkerState
from app.modules.processing.activity_service import record_activity
from app.modules.processing.workflow_service import StageResult, StageFailure, public_error
from app.modules.processing.worker_handlers import production_handlers
from app.modules.processing.worker_lock import WorkerLock, WorkerAlreadyRunning
from app.modules.processing.worker_queue import claim_next
from app.modules.processing.worker_recovery import recover_running, terminate

logger = logging.getLogger('leadvision.worker')


class StageContext:
    """Handlers must use bounded I/O and checkpoint during cooperative work."""
    def __init__(self, worker, job_id, job_deadline, stage_deadline, attempt=1):
        self.worker = worker
        self.job_id = job_id
        self.job_deadline = job_deadline
        self.stage_deadline = stage_deadline
        self.attempt = attempt

    def checkpoint(self):
        if self.worker.stop_event.is_set():
            raise StageFailure('JOB_INTERRUPTED', retryable=True)
        if time.monotonic() >= self.job_deadline:
            raise StageFailure('JOB_TIMEOUT', retryable=True)
        if time.monotonic() >= self.stage_deadline:
            raise StageFailure('STAGE_TIMEOUT', retryable=True)
        with self.worker.database.sessions() as session:
            job = session.get(Job, self.job_id)
            if job is None or job.cancel_requested:
                raise StageFailure('JOB_CANCELLED')
            if job.owner_token != self.worker.owner or job.status != 'running':
                raise StageFailure('JOB_INTERRUPTED', retryable=True)

    def wait(self, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.checkpoint()
            time.sleep(min(0.05, max(0, until - time.monotonic())))


class Worker:
    def __init__(self, database, settings, *, handlers=None):
        self.database = database
        self.settings = settings
        self.handlers = production_handlers() if handlers is None else handlers
        self.owner = str(uuid4())
        self.lock = WorkerLock(settings.data_dir)
        self.stop_event = Event()
        self.active = False
        self.monitor = None
        self.last_housekeeping = 0.0

    def __enter__(self):
        self.lock.acquire()
        try:
            with self.database.transaction(immediate=True) as session:
                recover_running(session)
                state = session.get(WorkerState, 1)
                state.owner_token = self.owner
                state.process_start_identity = f'{os.getpid()}:{self.owner}'
                state.heartbeat = utc_now()
                state.worker_paused = state.maintenance_requested
            self.monitor = Thread(target=self._heartbeat, name='worker-heartbeat', daemon=True)
            self.monitor.start()
            from app.modules.nlp.model_cache_service import refresh_runtime
            refresh_runtime(self.database, self.settings)
            return self
        except BaseException:
            self.stop_event.set()
            if self.monitor is not None:
                self.monitor.join(timeout=6)
            self.lock.release()
            raise

    def _heartbeat(self):
        while not self.stop_event.wait(0.5):
            try:
                with self.database.transaction(immediate=True) as session:
                    state = session.get(WorkerState, 1)
                    if state.owner_token != self.owner:
                        self.stop_event.set()
                        return
                    state.heartbeat = utc_now()
                    state.worker_paused = state.maintenance_requested and not self.active
            except Exception as exc:
                logger.warning('Heartbeat delayed (%s).', type(exc).__name__)

    def __exit__(self, *args):
        self.stop_event.set()
        if self.monitor is not None:
            self.monitor.join(timeout=6)
        try:
            with self.database.transaction(immediate=True) as session:
                state = session.get(WorkerState, 1)
                if state.owner_token == self.owner:
                    state.owner_token = None
                    state.heartbeat = None
                    state.process_start_identity = None
                    state.worker_paused = False
        finally:
            self.lock.release()

    def run_once(self):
        if time.monotonic() - self.last_housekeeping > 30:
            from app.modules.nlp.model_cache_service import refresh_runtime
            refresh_runtime(self.database, self.settings)
            from app.modules.evidence.evidence_service import housekeeping
            try:
                housekeeping(self.database, ArtifactStorage(self.settings.data_dir))
            except Exception as error:
                logger.warning('Artifact housekeeping delayed (%s).', type(error).__name__)
            self.last_housekeeping = time.monotonic()
        job_id = claim_next(self.database, self.owner)
        if job_id is None:
            return False
        self.active = True
        try:
            self._process(job_id)
        except Exception as exc:
            logger.error('Job failed (%s), job_id=%s', type(exc).__name__, job_id)
            with self.database.transaction(immediate=True) as session:
                job = session.get(Job, job_id)
                if job and job.status == 'running' and job.owner_token == self.owner:
                    terminate(session, job, 'failed', public_error('JOB_INTERNAL_ERROR', job.current_stage, True))
        finally:
            self.active = False
            self._knowledge_index_batch = None
        return True

    def _process(self, job_id):
        with self.database.sessions() as session:
            job = session.get(Job, job_id)
            snapshot = copy.deepcopy(job.input_snapshot)
            names = [stage.name for stage in repository.stages(session, job_id) if stage.name != 'finalize']
        deadline = time.monotonic() + self.settings.job_deadline_seconds
        outputs = {}
        failure = None
        independent_failure = None
        for name in names:
            handler = self.handlers.get(name)
            if handler is None:
                failure = StageFailure('STAGE_NOT_IMPLEMENTED')
                self._mark_failed(job_id, name, failure)
                break
            for attempt in (1, 2):
                with self.database.transaction(immediate=True) as session:
                    job = session.get(Job, job_id)
                    if job.owner_token != self.owner or job.status != 'running':
                        return
                    stage = session.scalar(select(JobStage).where(JobStage.job_id == job_id, JobStage.name == name))
                    stage.state = 'running'
                    stage.attempts = attempt
                    stage.started_at = stage.started_at or utc_now()
                    stage.input_hash = snapshot_hash({'snapshot': snapshot, 'upstream': outputs})
                    job.current_stage = name
                context = StageContext(self, job_id, deadline, min(deadline, time.monotonic() + self.settings.stage_deadline_seconds), attempt)
                try:
                    context.checkpoint()
                    result = StageResult.model_validate(handler(context, copy.deepcopy(snapshot), copy.deepcopy(outputs)))
                    context.checkpoint()
                    self._commit_stage(job_id, name, result)
                    outputs[name] = result.output
                    break
                except StageFailure as exc:
                    if exc.retryable and exc.code not in {'JOB_TIMEOUT', 'JOB_INTERRUPTED'} and attempt == 1:
                        continue
                    failure = exc
                except ValidationError:
                    failure = StageFailure('INVALID_STAGE_OUTPUT')
                except Exception as exc:
                    logger.error('Stage failed (%s), job_id=%s, stage=%s', type(exc).__name__, job_id, name)
                    failure = StageFailure('STAGE_FAILED')
                self._mark_failed(job_id, name, failure)
                break
            if failure is not None:
                independent = name in {'business_analysis', 'visual_metrics', 'semantic_match'} or (snapshot.get('request', {}).get('mode') == 'live' and name in {'acquire_text', 'acquire_image'})
                if independent and failure.code not in {'JOB_CANCELLED', 'JOB_TIMEOUT', 'STAGE_TIMEOUT', 'JOB_INTERRUPTED'}:
                    independent_failure = independent_failure or (failure, name)
                    failure = None
                    continue
                break
        with self.database.transaction(immediate=True) as session:
            job = session.get(Job, job_id)
            if job.status != 'running' or job.owner_token != self.owner:
                return
            stages = repository.stages(session, job_id)
            usable = any(stage.usable for stage in stages)
            cancelled = job.cancel_requested or (failure and failure.code == 'JOB_CANCELLED')
            complete = all(stage.state in {'succeeded', 'warning'} for stage in stages if stage.required)
            status = 'cancelled' if cancelled else ('completed' if complete and usable else ('partial' if usable else 'failed'))
            final = next(stage for stage in stages if stage.name == 'finalize')
            final.state = 'succeeded'
            final.attempts = 1
            final.started_at = final.finished_at = utc_now()
            final.output = {'status': status}
            reported_failure, reported_stage = independent_failure or (failure, job.current_stage)
            error = public_error(reported_failure.code, reported_stage, reported_failure.retryable) if reported_failure else None
            if cancelled:
                error = public_error('JOB_CANCELLED', job.current_stage)
            terminate(session, job, status, error)

    def _mark_failed(self, job_id, name, failure):
        with self.database.transaction(immediate=True) as session:
            job = session.get(Job, job_id)
            if job.status != 'running' or job.owner_token != self.owner:
                return
            stage = session.scalar(select(JobStage).where(JobStage.job_id == job_id, JobStage.name == name))
            stage.state = 'failed'
            stage.error = public_error(failure.code, name, failure.retryable)
            stage.finished_at = utc_now()
            job.current_stage = name

    def _commit_stage(self, job_id, name, result):
        with self.database.transaction(immediate=True) as session:
            job = session.get(Job, job_id)
            if job.status != 'running' or job.owner_token != self.owner:
                raise StageFailure('JOB_INTERRUPTED', retryable=True)
            stage = session.scalar(select(JobStage).where(JobStage.job_id == job_id, JobStage.name == name))
            if stage.state in {'succeeded', 'warning', 'skipped'}:
                return
            stage.state = 'warning' if result.warnings and result.state == 'succeeded' else result.state
            stage.output = result.output
            if name == 'index_knowledge':
                from app.modules.knowledge.knowledge_index_service import persist_index
                persist_index(session, job, result, getattr(self, '_knowledge_index_batch', None))
            if name == 'prepare_outreach':
                from app.modules.outreach.outreach_worker import persist
                persist(session, job, result)
            from app.modules.evidence.evidence_service import persist_stage_evidence
            persist_stage_evidence(session, job, name, result)
            from app.modules.evidence.live_evidence_service import persist as persist_live
            persist_live(session, job, name, result)
            from app.modules.nlp.business_analysis_service import persist_analysis
            persist_analysis(session, job, name, result)
            from app.modules.computer_vision.vision_service import persist_visual
            persist_visual(session, job, name, result)
            from app.modules.semantics.semantic_matching_service import persist_semantic
            persist_semantic(session, job, name, result)
            from app.modules.scoring.scoring_service import persist_score
            persist_score(session, job, name, result)
            stage.usable = result.usable
            stage.warnings = result.warnings
            stage.finished_at = utc_now()
            record_activity(session, action=f'{job.kind}.stage_saved', origin='worker', agency_id=job.agency_id,
                            campaign_id=job.input_snapshot.get('campaign_id'), lead_id=job.lead_id,
                            event_key=f'job:{job.id}:stage:{name}:saved', new_value={'job_id': job.id, 'stage': name})

    def run_forever(self):
        while not self.stop_event.is_set():
            if not self.run_once():
                self.stop_event.wait(self.settings.worker_poll_seconds)


def main():
    settings = Settings()
    ArtifactStorage(settings.data_dir)
    database = Database(settings)
    logging.basicConfig(level=settings.log_level)
    try:
        migrate(database.engine, require_initialized=settings.database_must_exist)
        with Worker(database, settings) as worker:
            logger.info('Worker ready (PID %s); live/saved evidence, NLP, image metrics, semantic matching and explained scoring are implemented.', os.getpid())
            worker.run_forever()
    except WorkerAlreadyRunning:
        print('A worker is already running for this project. Use the existing worker.')
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print('Worker stopped. Interrupted work is recovered on the next worker start.')
    finally:
        database.close()


if __name__ == '__main__':
    main()
