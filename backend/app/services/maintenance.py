"""Foundational pause flag; full coordinated backup arrives in module 19."""

from sqlalchemy.orm import Session

from app.db.session import Database
from app.models.maintenance import WorkerState


def is_maintenance_active(database: Database) -> bool:
    with database.sessions() as session:
        state = session.get(WorkerState, 1)
        if state is None:
            raise RuntimeError("Missing maintenance state.")
        return state.maintenance_requested


def set_maintenance(session: Session, *, active: bool, reason: str | None = None) -> None:
    if active and (not reason or not reason.strip()):
        raise ValueError("Maintenance requires a reason.")
    if reason and len(reason) > 500:
        raise ValueError("Maintenance reason is too long.")
    state = session.get(WorkerState, 1)
    if state is None:
        raise RuntimeError("Missing maintenance state.")
    state.maintenance_requested = active
    state.maintenance_reason = reason if active else None
