from uuid import uuid4
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.clock import utc_now
from app.db.base import Base


class Lead(Base):
    __tablename__ = 'leads'
    __table_args__ = (
        UniqueConstraint('campaign_id', 'company_id'),
        CheckConstraint('employee_count IS NULL OR employee_count >= 0'),
        CheckConstraint('revision >= 1 AND analytical_input_revision >= 1'),
        CheckConstraint('length(trim(company_name)) BETWEEN 1 AND 200'),
        CheckConstraint("pipeline_state IN ('New','Reviewed','Qualified','Contacted','Replied','Converted','Lost')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id', ondelete='RESTRICT'), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='RESTRICT'), index=True)
    company_name: Mapped[str] = mapped_column(String(200), index=True)
    name_key: Mapped[str] = mapped_column(String(200), index=True)
    website: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(2))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    pipeline_state: Mapped[str] = mapped_column(String(20), default='New')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    analytical_input_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
    updated_at: Mapped[str] = mapped_column(String(32), default=utc_now)
