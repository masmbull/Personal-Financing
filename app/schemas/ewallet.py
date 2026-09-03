"""E-wallet / e-money provider schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProviderBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    legal_name: str = Field(min_length=1, max_length=200)
    short_name: str = Field(min_length=1, max_length=80)
    aliases: Optional[str] = None
    operator_type: Optional[str] = Field(None, max_length=40)
    active: bool = True
    source: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=40)
    legal_name: Optional[str] = Field(None, min_length=1, max_length=200)
    short_name: Optional[str] = Field(None, min_length=1, max_length=80)
    aliases: Optional[str] = None
    operator_type: Optional[str] = Field(None, max_length=40)
    active: Optional[bool] = None
    source: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    effective_from: Optional[date] = None
    effective_until: Optional[date] = None


class ProviderResponse(ProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    verified_at: Optional[datetime] = None


class ProviderListResponse(BaseModel):
    items: list[ProviderResponse]
    total: int
