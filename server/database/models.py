"""ORM models."""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .session import Base


def new_id() -> str:
    """Primary keys are uuid4 text, so an id is known before the row is flushed
    and stays unique across databases -- no autoincrement counter anywhere."""
    return str(uuid.uuid4())


class Company(Base):
    """A company and what it does.

    Companies are looked up by name alone, so the name is the natural key: one
    row per company.
    """

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    details: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Company {self.name!r}>"


class Conclusion(Base):
    """One problem found in a company's office, plus every solution proposed for it.

    No FK to Company: a conclusion can be recorded before a matching company
    row exists, so company_name is kept as a plain string, same as
    determine_problems() already takes it.
    """

    __tablename__ = "conclusions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
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

    Deliberately just the id: the solution's content lives with the pipeline
    output inside Conclusion.solutions and gets joined on there, so nothing is
    duplicated here. It is the primary key, which is what makes accepting the
    same solution twice a no-op.
    """

    __tablename__ = "accepted_solutions"

    solution_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)

    def __repr__(self) -> str:
        return f"<AcceptedSolution {self.solution_uuid!r}>"
