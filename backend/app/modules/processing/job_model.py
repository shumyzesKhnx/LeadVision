"""Durable analysis queue and bounded stage outcomes."""
from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.clock import utc_now
from app.modules.foundation.database_base import Base


class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = (UniqueConstraint('agency_id', 'scope', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agency_id: Mapped[str] = mapped_column(ForeignKey('agencies.id', ondelete='RESTRICT'))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(30), default='analysis')
    status: Mapped[str] = mapped_column(String(20), default='queued')
    current_stage: Mapped[str | None] = mapped_column(String(50))
    request_hash: Mapped[str] = mapped_column(String(64))
    request_body: Mapped[dict] = mapped_column(JSON)
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(100))
    owner_token: Mapped[str | None] = mapped_column(String(36))
    cancel_requested: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    retry_of_id: Mapped[str | None] = mapped_column(ForeignKey('jobs.id', ondelete='SET NULL'))
    error: Mapped[dict | None] = mapped_column(JSON)
    queued_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))


class JobStage(Base):
    __tablename__ = 'job_stages'
    __table_args__ = (UniqueConstraint('job_id', 'name'), CheckConstraint('attempts BETWEEN 0 AND 2'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(50))
    ordinal: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    input_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict | None] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[dict | None] = mapped_column(JSON)
    usable: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    required: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=True)
    started_at: Mapped[str | None] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
