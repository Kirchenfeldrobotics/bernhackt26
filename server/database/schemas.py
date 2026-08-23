from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, field_validator

# primary keys were an autoincrement counter before the uuid migration, and a
# column's type cannot be changed in place, so rows written back then still hold
# integers; serve both as text rather than 500 on the old ones
IdText = Annotated[str, BeforeValidator(str)]

# what a caller may set on a company
class CompanyIn(BaseModel):
    name: str
    website: Optional[str] = None
    details: Optional[str] = None

    # a company is looked up by name, so a blank one is unusable
    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


# a company as the api returns it
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: IdText
    name: str
    website: Optional[str]
    details: Optional[str]
    created_at: datetime


# the body the headset posts to /accept-solution
class AcceptedSolutionIn(BaseModel):
    solution_uuid: str

    # reject blanks before they reach the table as a key
    @field_validator("solution_uuid")
    @classmethod
    def uuid_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("solution_uuid must not be empty")
        return v


# a company name on its own, for lookups by body
class CompanyNameIn(BaseModel):
    company_name: str

    # same normalisation every other entry point applies
    @field_validator("company_name")
    @classmethod
    def company_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company_name must not be empty")
        return v


# the conclusion an accepted solution came from
class AcceptedSolutionConclusion(BaseModel):
    """The conclusion an accepted solution was proposed for."""

    model_config = ConfigDict(from_attributes=True)

    id: IdText
    batch: str
    title: str
    problem: str
    savings_10y_chf: str
    anchor: dict[str, Any]
    created_at: datetime


# one accepted solution with its surrounding conclusion
class AcceptedSolutionOut(BaseModel):
    """One accepted solution, with the conclusion it belongs to."""

    solution: dict[str, Any]
    conclusion: AcceptedSolutionConclusion


# a stored conclusion row exactly as /receive-data persisted it
class ConclusionOut(BaseModel):
    """One conclusion as it was written to the database."""

    model_config = ConfigDict(from_attributes=True)

    id: IdText
    company_name: str
    batch: str
    title: str
    problem: str
    solutions: list[dict[str, Any]]
    savings_10y_chf: str
    anchor: dict[str, Any]
    status: str
    created_at: datetime
