"""Category request/response schemas."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import TransactionType


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: TransactionType = Field(description="EXPENSE or INCOME")
    group: Optional[str] = Field(None, max_length=50)
    icon: Optional[str] = Field(None, max_length=10)
    parent_id: Optional[int] = Field(None, description="Parent category id (NULL for root)")


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[TransactionType] = None
    group: Optional[str] = Field(None, max_length=50)
    icon: Optional[str] = Field(None, max_length=10)
    parent_id: Optional[int] = Field(None, description="Parent category id (NULL for root)")


class CategoryResponse(CategoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_default: Optional[int] = None
    parent_id: Optional[int] = None
    has_children: Optional[bool] = None


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]
    total: int
