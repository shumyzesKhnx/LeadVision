from uuid import uuid4
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


class ReviewerOverride(Base):
    __tablename__ = 'reviewer_overrides'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'))
    score_id: Mapped[str] = mapped_column(ForeignKey('score_runs.id', ondelete='CASCADE'))
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(1000))
    reviewer: Mapped[str] = mapped_column(String(100))
    binding: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
