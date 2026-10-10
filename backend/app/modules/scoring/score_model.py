from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


class ScoreRun(Base):
    __tablename__ = 'score_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('analysis_runs.id', ondelete='CASCADE'), unique=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'))
    result: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)


class ScoreComponent(Base):
    __tablename__ = 'score_components'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    score_id: Mapped[str] = mapped_column(ForeignKey('score_runs.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)
