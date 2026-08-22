"""ORM models."""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .session import Base


class Company(Base):
    """A company and the category assigned to it.

    Categories are assigned by company name alone, so the name is the natural
    key: one row per company, carrying its category.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    details: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Company {self.name!r} category={self.category!r}>"
