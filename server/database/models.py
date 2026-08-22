"""ORM models."""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, func
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


class Conclusion(Base):
    """One problem found in a company's office, plus every solution proposed for it.

    No FK to Company: a conclusion can be recorded before a matching company
    row exists, so company_name is kept as a plain string, same as
    determine_problems() already takes it.
    """

    __tablename__ = "conclusions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    batch: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    problem: Mapped[str] = mapped_column(Text)
    # List of {"id", "name", "url", "description"} dicts -- no separate
    # solutions table, so "id" here is just a stable identifier within this
    # list, not a DB primary key.
    solutions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    savings_10y_chf: Mapped[str] = mapped_column(Text)
    # {"label": ..., "position": {"x": ..., "y": ..., "z": ...}}
    anchor: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Conclusion {self.id} company={self.company_name!r} batch={self.batch!r}>"


class AcceptedSolution(Base):
    """A solution the user accepted in VR.

    Deliberately just the uuid: the solution's content lives with the pipeline
    output and gets joined on later, so nothing is duplicated here. The uuid is
    the primary key, which is what makes accepting the same one twice a no-op.
    """

    __tablename__ = "accepted_solutions"

    solution_uuid: Mapped[str] = mapped_column(String(64), primary_key=True)

    def __repr__(self) -> str:
        return f"<AcceptedSolution {self.solution_uuid!r}>"
