"""Campaign identity; archiving preserves linked history."""

from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utc_now
from app.db.base import Base


class Campaign(Base):
    __tablename__ = 'campaigns'
    __table_args__ = (
        CheckConstraint('length(trim(name)) BETWEEN 1 AND 200', name='ck_campaign_name'),
        CheckConstraint('revision >= 1', name='ck_campaign_revision'),
        ForeignKeyConstraint(['agency_id', 'icp_id'], ['icps.agency_id', 'icps.id'], ondelete='RESTRICT'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agency_id: Mapped[str] = mapped_column(ForeignKey('agencies.id', ondelete='RESTRICT'), index=True)
    icp_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now)
