"""Saved upload ownership and source-labelled evidence, separate from reviews."""
from uuid import uuid4
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.core.clock import utc_now


class SavedEvidenceUpload(Base):
    __tablename__ = 'saved_evidence_uploads'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    source_mode: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default='staging')
    manifest: Mapped[dict] = mapped_column(JSON)
    attached_job_id: Mapped[str | None] = mapped_column(ForeignKey('jobs.id', ondelete='SET NULL'))
    imported_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    expires_at: Mapped[str] = mapped_column(String(32))


class Evidence(Base):
    __tablename__ = 'evidence'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('analysis_runs.id', ondelete='CASCADE'), index=True)
    saved_upload_id: Mapped[str] = mapped_column(ForeignKey('saved_evidence_uploads.id', ondelete='CASCADE'))
    kind: Mapped[str] = mapped_column(String(10))
    source_mode: Mapped[str] = mapped_column(String(20))
    original_url: Mapped[str | None] = mapped_column(String(2048))
    collected_at: Mapped[str | None] = mapped_column(String(32))
    imported_at: Mapped[str] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    usable: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=True)
    review_reason: Mapped[str | None] = mapped_column(String(500))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now)
