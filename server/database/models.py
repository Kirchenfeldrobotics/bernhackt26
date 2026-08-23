import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from .session import Base


# uuid4 primary keys, so an id exists before the row is flushed
def new_id() -> str:
    return str(uuid.uuid4())


# a company and what it does; the name is the natural key
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    details: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Company {self.name!r}>"


# one problem found in a company's office plus every fix proposed for it
class Conclusion(Base):
    __tablename__ = "conclusions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    batch: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    problem: Mapped[str] = mapped_column(Text)
    # no solutions table: they live here as json, keyed by the id save_plan stamps
    solutions: Mapped[list[dict[str, Any]]] = mapped_column(MutableList.as_mutable(JSON))
    savings_10y_chf: Mapped[str] = mapped_column(Text)
    anchor: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Conclusion {self.id} company={self.company_name!r} batch={self.batch!r}>"


# a solution the headset marked as chosen, by id alone
class AcceptedSolution(Base):
    __tablename__ = "accepted_solutions"

    solution_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)

    def __repr__(self) -> str:
        return f"<AcceptedSolution {self.solution_uuid!r}>"
