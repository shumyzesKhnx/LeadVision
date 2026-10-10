"""An activity is a recorded event, not an automatic sales decision."""

from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.foundation.clock import utc_now
from app.modules.foundation.database_base import Base


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('operator','api','worker','import','n8n')", name="ck_activity_origin"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agency_id: Mapped[str | None] = mapped_column(ForeignKey("agencies.id", ondelete="RESTRICT"))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="RESTRICT"), index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_label: Mapped[str | None] = mapped_column(String(200))
    old_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    event_key: Mapped[str | None] = mapped_column(Text, unique=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now, nullable=False)
