import os
import subprocess
from threading import Event, Thread
import time
import pytest
from sqlalchemy import select, func
from app.core.config import BACKEND_ROOT, PROJECT_ROOT
from app.models.activity import Activity
from app.models.maintenance import WorkerState
from app.services.workflow import StageResult, STAGES
from app.services.maintenance import set_maintenance
from app.worker.main import Worker
from app.worker.lock import WorkerAlreadyRunning
from test_job_idempotency import queue


def test_second_worker_is_rejected_even_with_old_heartbeat(client, application, settings, registered_worker):
    with application.state.database.transaction(immediate=True) as session:
        session.get(WorkerState, 1).heartbeat = '2000-01-01T00:00:00Z'
    with pytest.raises(WorkerAlreadyRunning):
        with Worker(application.state.database, settings):
            pass
    child = subprocess.run([str(PROJECT_ROOT / '.venv/Scripts/python.exe'), '-m', 'app.worker.main'],
                           cwd=BACKEND_ROOT, env={**os.environ, 'LEADVISION_DATA_DIR': str(settings.data_dir)},
                           capture_output=True, timeout=10)
    assert child.returncode == 1
    assert b'already running' in child.stdout


def test_crud_poll_and_cancel_work_during_slow_stage(client, job_lead, application, settings):
    settings.sqlite_busy_timeout_ms = 2000
    entered = Event()
    def slow(context, snapshot, outputs):
        entered.set()
        context.wait(5)
        return StageResult(output={'test_only': True}, usable=True)
    def success(context, snapshot, outputs):
        return StageResult(output={'test_only': True}, usable=True)
    handlers = {name: success for name in STAGES}
    handlers['acquire_image'] = slow
    with Worker(application.state.database, settings, handlers=handlers) as worker:
        queued = queue(client, job_lead).json()
        runner = Thread(target=worker.run_once)
        runner.start()
        try:
            assert entered.wait(5)
            start = time.monotonic()
            result = client.patch(f"/api/v1/leads/{job_lead['id']}", json={'notes': 'Still responsive'}, headers={'If-Match': '"1"'})
            assert result.status_code == 200
            assert time.monotonic() - start < 2
            assert client.get(queued['poll_url']).json()['status'] == 'running'
            assert client.post(f"/api/v1/jobs/{queued['job_id']}/cancel").status_code == 200
            runner.join(timeout=5)
            assert not runner.is_alive()
            finished = client.get(queued['poll_url']).json()
            assert finished['status'] == 'cancelled'
            assert finished['stages'][1]['usable']  # Previously committed text remains.
        finally:
            if runner.is_alive():
                worker.stop_event.set()
                runner.join(timeout=6)


def test_stage_save_deduplicates_activity_and_maintenance_pauses_claim(client, job_lead, application, settings):
    from app.worker.queue import claim_next
    with Worker(application.state.database, settings) as worker:
        queued = queue(client, job_lead).json()
        with application.state.database.transaction(immediate=True) as session:
            set_maintenance(session, active=True, reason='Test pause')
        assert claim_next(worker.database, worker.owner) is None
        with application.state.database.transaction(immediate=True) as session:
            set_maintenance(session, active=False)
        assert claim_next(worker.database, worker.owner) == queued['job_id']
        result = StageResult(output={'test_only': True}, usable=True)
        worker._commit_stage(queued['job_id'], 'acquire_text', result)
        worker._commit_stage(queued['job_id'], 'acquire_text', StageResult(output={'different': True}))
        with application.state.database.sessions() as session:
            assert session.scalar(select(func.count()).select_from(Activity).where(
                Activity.event_key == f"job:{queued['job_id']}:stage:acquire_text:saved")) == 1
        polled = client.get(queued['poll_url']).json()
        assert polled['stages'][1]['output'] == {'test_only': True}
