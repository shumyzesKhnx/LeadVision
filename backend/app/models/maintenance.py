"""Durable maintenance state and a retryable file-deletion outbox."""

from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utc_now
from app.db.base import Base


class WorkerState(Base):
    __tablename__ = "worker_state"
    __table_args__ = (CheckConstraint("singleton = 1", name="ck_worker_singleton"),)

    singleton: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    owner_token: Mapped[str | None] = mapped_column(String(36))
    heartbeat: Mapped[str | None] = mapped_column(String(32))
    process_start_identity: Mapped[str | None] = mapped_column(String(100))
    maintenance_requested: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), default=False, nullable=False
    )
    worker_paused: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True), default=False, nullable=False
    )
    maintenance_reason: Mapped[str | None] = mapped_column(String(500))


class FileCleanupTask(Base):
    __tablename__ = "file_cleanup_tasks"
    __table_args__ = (
        CheckConstraint("state IN ('pending','completed','failed')", name="ck_cleanup_state"),
        CheckConstraint("attempts >= 0", name="ck_cleanup_attempts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    artifact_key: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(32))
    # Optional batching link: the deletion request's recorded event owns its tasks.
    activity_id: Mapped[str | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL")
    )
