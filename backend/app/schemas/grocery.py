import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class GroceryItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: float = Field(gt=0, le=100_000)
    unit: str = Field(min_length=1, max_length=16)
    checked: bool = False
    notes: str | None = Field(default=None, max_length=200)


class GroceryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    quantity: float
    unit: str
    checked: bool
    position: int
    notes: str | None


class GroceryListCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)


class GroceryListUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1, max_length=200)]
    items: list[GroceryItemIn] = Field(min_length=1, max_length=500)
    expected_revision: int | None = Field(default=None, ge=1)


class GroceryListSummary(BaseModel):
    id: uuid.UUID
    title: str
    plan_id: uuid.UUID | None
    revision: int
    item_count: int
    checked_count: int
    created_at: datetime
    updated_at: datetime


class GroceryListDetail(GroceryListSummary):
    items: list[GroceryItemOut]