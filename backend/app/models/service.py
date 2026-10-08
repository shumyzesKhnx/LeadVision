"""Services are deactivated, preserving their IDs for future draft history."""

from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utc_now
from app.db.base import Base


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 200", name="ck_service_name"),
        CheckConstraint("length(trim(description)) BETWEEN 1 AND 5000", name="ck_service_description"),
        CheckConstraint("revision >= 1", name="ck_service_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now, nullable=False)
