"""Editable profile identity and immutable analytical snapshots."""

from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utc_now
from app.db.base import Base


class ICP(Base):
    __tablename__ = 'icps'
    __table_args__ = (
        Index('ux_icps_agency_id_id', 'agency_id', 'id', unique=True),
        CheckConstraint('length(trim(name)) BETWEEN 1 AND 200', name='ck_icp_name'),
        CheckConstraint('revision >= 1', name='ck_icp_revision'),
        ForeignKeyConstraint(['id', 'current_version_id'], ['icp_versions.icp_id', 'icp_versions.id'],
                             ondelete='RESTRICT', name='fk_icp_current_owner'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agency_id: Mapped[str] = mapped_column(ForeignKey('agencies.id', ondelete='RESTRICT'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    archived: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now)


class ICPVersion(Base):
    __tablename__ = 'icp_versions'
    __table_args__ = (
        UniqueConstraint('icp_id', 'version'),
        UniqueConstraint('icp_id', 'id'),
        CheckConstraint('version >= 1', name='ck_icp_version'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    icp_id: Mapped[str] = mapped_column(ForeignKey('icps.id', ondelete='RESTRICT'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON)
    score_rule_version: Mapped[str] = mapped_column(String(50))
    content_hash: Mapped[str] = mapped_column(String(64))
    semantic_input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
