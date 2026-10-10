"""The one local agency workspace."""

from uuid import uuid4

from sqlalchemy import CheckConstraint, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.foundation.clock import utc_now
from app.modules.foundation.database_base import Base


class Agency(Base):
    __tablename__ = "agencies"
    __table_args__ = (
        CheckConstraint("singleton_key = 1", name="ck_agency_singleton"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="ck_agency_name"),
        CheckConstraint("revision >= 1", name="ck_agency_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    singleton_key: Mapped[int] = mapped_column(Integer, unique=True, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[dict | None] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now, nullable=False)
