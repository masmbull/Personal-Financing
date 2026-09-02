"""PaymentMethod schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import PaymentMethodType


class PaymentMethodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    method_type: PaymentMethodType
    source: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class PaymentMethodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    method_type: Optional[PaymentMethodType] = None
    active: Optional[bool] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    method_type: str
    active: bool = True
    source: Optional[str] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PaymentMethodListResponse(BaseModel):
    items: list[PaymentMethodResponse]
    total: int
