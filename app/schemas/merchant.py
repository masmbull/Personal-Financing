"""Merchant schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import MerchantType


class MerchantCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    category_id: Optional[int] = None
    merchant_type: MerchantType = MerchantType.OTHER
    source: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=500)
    aliases: Optional[list[str]] = None


class MerchantUpdate(BaseModel):
    canonical_name: Optional[str] = Field(None, min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    category_id: Optional[int] = None
    merchant_type: Optional[MerchantType] = None
    active: Optional[bool] = None
    source: Optional[str] = None
    source_url: Optional[str] = None


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    source: Optional[str] = None


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    canonical_name: str
    display_name: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    merchant_type: str
    active: bool = True
    source: Optional[str] = None
    source_url: Optional[str] = None
    aliases: list[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MerchantListResponse(BaseModel):
    items: list[MerchantResponse]
    total: int


class MerchantResolveRequest(BaseModel):
    text: str = Field(min_length=1)


class MerchantResolveResponse(BaseModel):
    merchant_id: Optional[int] = None
    matched_alias: Optional[str] = None
    confidence: Optional[float] = None
    match_method: Optional[str] = None
    ambiguous: Optional[bool] = None
    matches: Optional[list[dict]] = None
