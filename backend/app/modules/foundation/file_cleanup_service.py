"""Queue file deletion with the business transaction; delete only after commit."""

from sqlalchemy.orm import Session

from app.modules.foundation.clock import utc_now
from app.modules.foundation.storage import ArtifactStorage
from app.modules.foundation.maintenance_model import FileCleanupTask


def queue_cleanup(
    session: Session,
    storage: ArtifactStorage,
    *,
    artifact_key: str,
    reason: str,
    activity_id: str | None = None,
) -> FileCleanupTask:
    storage.resolve(artifact_key)
    if not reason.strip() or len(reason) > 200:
        raise ValueError("A bounded cleanup reason is required.")
    task = FileCleanupTask(artifact_key=artifact_key, reason=reason, activity_id=activity_id)
    session.add(task)
    session.flush()
    return task


def perform_cleanup(session: Session, storage: ArtifactStorage, task_id: str) -> None:
    """Caller opens a new transaction after the business deletion committed."""
    task = session.get(FileCleanupTask, task_id)
    if task is None or task.state == "completed":
        return
    task.attempts += 1
    try:
        storage.delete(task.artifact_key)
    except (OSError, ValueError):
        task.state = "failed"
        task.last_error = "FILE_CLEANUP_FAILED"
    else:
        task.state = "completed"
        task.last_error = None
        task.completed_at = utc_now()
