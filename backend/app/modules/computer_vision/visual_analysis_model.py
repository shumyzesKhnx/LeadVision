from uuid import uuid4
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


class VisualAnalysis(Base):
    __tablename__ = 'visual_analyses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey('analysis_runs.id', ondelete='CASCADE'), unique=True)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey('evidence.id', ondelete='CASCADE'), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
