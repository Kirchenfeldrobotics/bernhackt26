"""ORM models."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class Problem(Base):
    """One problem found in a company's office during one scan batch.

    No FK to Company: a problem can be recorded before a matching company row
    exists, so company_name is kept as a plain string, same as
    determine_problems() already takes it.
    """

    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    batch: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    solutions: Mapped[list["Solution"]] = relationship(
        back_populates="problem", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Problem {self.id} company={self.company_name!r} batch={self.batch!r}>"


class Solution(Base):
    """One product/service recommendation Gemini gave to fix a Problem."""

    __tablename__ = "solutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    explanation: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    problem: Mapped["Problem"] = relationship(back_populates="solutions")

    def __repr__(self) -> str:
        return f"<Solution {self.title!r} problem_id={self.problem_id}>"


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
