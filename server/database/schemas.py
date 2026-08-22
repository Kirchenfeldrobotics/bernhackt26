"""Request/response models for the company endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from . import categories


class CompanyIn(BaseModel):
    name: str
    category: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("category")
    @classmethod
    def category_known(cls, v: Optional[str]) -> Optional[str]:
        if not categories.is_valid(v):
            raise ValueError(f"unknown category {v!r}; known: {categories.CATEGORIES}")
        return v


class CategoryIn(BaseModel):
    category: Optional[str] = None

    @field_validator("category")
    @classmethod
    def category_known(cls, v: Optional[str]) -> Optional[str]:
        if not categories.is_valid(v):
            raise ValueError(f"unknown category {v!r}; known: {categories.CATEGORIES}")
        return v


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str]
    created_at: datetime
