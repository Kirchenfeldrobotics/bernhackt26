"""Request/response models for the company endpoints."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator

class CompanyIn(BaseModel):
    name: str
    website: Optional[str] = None
    details: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    website: Optional[str]
    details: Optional[str]
    created_at: datetime


class AcceptedSolutionIn(BaseModel):
    solution_uuid: str

    @field_validator("solution_uuid")
    @classmethod
    def uuid_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("solution_uuid must not be empty")
        return v


class CompanyNameIn(BaseModel):
    company_name: str

    @field_validator("company_name")
    @classmethod
    def company_name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company_name must not be empty")
        return v


class AcceptedSolutionConclusion(BaseModel):
    """The conclusion an accepted solution was proposed for."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    batch: str
    title: str
    problem: str
    savings_10y_chf: str
    anchor: dict[str, Any]
    created_at: datetime


class AcceptedSolutionOut(BaseModel):
    """One accepted solution, with the conclusion it belongs to."""

    solution: dict[str, Any]
    conclusion: AcceptedSolutionConclusion
