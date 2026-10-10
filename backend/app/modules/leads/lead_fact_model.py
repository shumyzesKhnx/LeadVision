from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.clock import utc_now
from app.modules.foundation.database_base import Base


class LeadFact(Base):
    __tablename__ = 'lead_facts'
    __table_args__ = (
        UniqueConstraint('lead_id', 'field_name', 'revision'),
        CheckConstraint('revision >= 1'),
        CheckConstraint("source_category IN ('user_provided','source_extracted','model_inferred')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[str | int | None] = mapped_column(JSON, nullable=False)
    source_category: Mapped[str] = mapped_column(String(30), default='user_provided')
    verified: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    actor_label: Mapped[str | None] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer)
    supersedes_fact_id: Mapped[str | None] = mapped_column(String(36))
    correction_reason: Mapped[str | None] = mapped_column(String(500))
    recorded_at: Mapped[str] = mapped_column(String(32), default=utc_now)
