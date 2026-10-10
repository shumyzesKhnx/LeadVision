from uuid import uuid4
from sqlalchemy import ForeignKey, String, Integer, LargeBinary, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.foundation.database_base import Base
from app.modules.foundation.clock import utc_now


class EmbeddingRuntime(Base):
    __tablename__ = 'embedding_runtime'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    identity: Mapped[dict] = mapped_column(JSON)
    checked_at: Mapped[str] = mapped_column(String(32), default=utc_now)


class Embedding(Base):
    __tablename__ = 'embeddings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agency_id: Mapped[str] = mapped_column(ForeignKey('agencies.id', ondelete='RESTRICT'))
    purpose: Mapped[str] = mapped_column(String(20))
    input_hash: Mapped[str] = mapped_column(String(64))
    space_hash: Mapped[str] = mapped_column(String(64))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)


class EmbeddingLead(Base):
    __tablename__ = 'embedding_leads'
    embedding_id: Mapped[str] = mapped_column(ForeignKey('embeddings.id', ondelete='CASCADE'), primary_key=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), primary_key=True)
