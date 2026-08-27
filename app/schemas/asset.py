"""Asset record schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    asset_type: str = Field(max_length=50, examples=["Kendaraan", "Properti"])
    current_value: int = Field(ge=0)
    purchase_value: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date] = None
    icon: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    asset_type: Optional[str] = Field(None, max_length=50)
    current_value: Optional[int] = Field(None, ge=0)
    purchase_value: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date] = None
    icon: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None


class AssetResponse(AssetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gain_loss: Optional[int] = Field(
        description="current_value - purchase_value (null when no purchase value)"
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    total_value: int
