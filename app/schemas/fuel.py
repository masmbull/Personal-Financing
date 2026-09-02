"""Fuel/BBM schemas (read-only master data)."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FuelBrandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    country: str = "ID"
    active: bool = True
    source: Optional[str] = None
    source_url: Optional[str] = None
    verified_at: Optional[datetime] = None


class FuelProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    brand_id: int
    brand_name: Optional[str] = None
    name: str
    product_code: Optional[str] = None
    fuel_type: Optional[str] = None
    ron: Optional[int] = None
    cn: Optional[int] = None
    specification: Optional[str] = None
    active: bool = True


class FuelPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    region: str
    price_per_liter: int
    currency: str = "IDR"
    effective_from: date
    effective_until: Optional[date] = None
    source: Optional[str] = None
    source_url: Optional[str] = None


class FuelBrandListResponse(BaseModel):
    items: list[FuelBrandResponse]
    total: int


class FuelProductListResponse(BaseModel):
    items: list[FuelProductResponse]
    total: int
