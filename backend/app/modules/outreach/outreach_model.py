from uuid import uuid4
from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


def identifier():
    return str(uuid4())


class OutreachDraft(Base):
    __tablename__ = 'outreach_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    agency_id: Mapped[str] = mapped_column(ForeignKey('agencies.id', ondelete='RESTRICT'))
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), unique=True)
    service_id: Mapped[str] = mapped_column(ForeignKey('services.id', ondelete='RESTRICT'))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    grounding: Mapped[dict] = mapped_column(JSON)
    retrieval: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)


class OutreachRevision(Base):
    __tablename__ = 'outreach_revisions'
    __table_args__ = (UniqueConstraint('draft_id', 'number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    draft_id: Mapped[str] = mapped_column(ForeignKey('outreach_drafts.id', ondelete='CASCADE'))
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    claims: Mapped[list] = mapped_column(JSON)
    unresolved_claims: Mapped[list] = mapped_column(JSON, default=list)
    reviewer: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)


class DraftSource(Base):
    __tablename__ = 'draft_sources'
    __table_args__ = (UniqueConstraint('draft_id', 'source_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    draft_id: Mapped[str] = mapped_column(ForeignKey('outreach_drafts.id', ondelete='CASCADE'))
    source_id: Mapped[str] = mapped_column(String(100))
    snapshot: Mapped[dict] = mapped_column(JSON)
