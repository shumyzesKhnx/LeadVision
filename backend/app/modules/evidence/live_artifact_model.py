from uuid import uuid4
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


class LiveArtifact(Base):
    __tablename__ = 'live_artifacts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey('analysis_runs.id', ondelete='CASCADE'))
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'))
    kind: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20), default='staging')
    metadata_json: Mapped[dict] = mapped_column(JSON)
    original_url: Mapped[str] = mapped_column(String(2048))
    collected_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    expires_at: Mapped[str] = mapped_column(String(32))
