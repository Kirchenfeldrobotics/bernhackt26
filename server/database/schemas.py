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
class AcceptedConclusionIn(BaseModel):
    """The conclusion the user accepted in VR, by its row id.

    A conclusion is what gets accepted -- not the solutions inside it, which are
    that one conclusion's detail and carry no ids of their own.
    """

    conclusion_id: str

    # reject blanks before they reach the database as a key
    @field_validator("conclusion_id")
    @classmethod
    def conclusion_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("conclusion_id must not be empty")
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


# a stored conclusion row exactly as /receive-data persisted it
class ConclusionOut(BaseModel):
    """One conclusion as it was written to the database.

    This is the whole unit: the problem, every solution proposed for it, what it
    saves and where its panel floats. `status` says whether it was accepted in
    VR; /get-accepted-solutions returns these, filtered to the accepted ones.
    """

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
