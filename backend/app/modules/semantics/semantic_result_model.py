from uuid import uuid4
from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


class SemanticResult(Base):
    __tablename__ = 'semantic_results'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey('analysis_runs.id', ondelete='CASCADE'), unique=True)
    company_embedding_id: Mapped[str | None] = mapped_column(ForeignKey('embeddings.id'))
    icp_embedding_id: Mapped[str | None] = mapped_column(ForeignKey('embeddings.id'))
    result: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
