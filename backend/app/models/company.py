from uuid import uuid4
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.clock import utc_now
from app.db.base import Base


class Company(Base):
    __tablename__ = 'companies'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    normalized_domain: Mapped[str] = mapped_column(String(253), unique=True)
    created_at: Mapped[str] = mapped_column(String(32), default=utc_now)
