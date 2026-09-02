"""Fuel/BBM API — read-only master data + price lookup (requires auth)."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.fuel import (
    FuelBrandListResponse, FuelBrandResponse, FuelPriceResponse,
    FuelProductListResponse, FuelProductResponse,
)
from app.services import fuel as svc

router = APIRouter(prefix="/fuel", tags=["fuel"])


@router.get("/brands", response_model=FuelBrandListResponse)
def list_brands(db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    items = [FuelBrandResponse.model_validate(b) for b in svc.list_brands(db)]
    return FuelBrandListResponse(items=items, total=len(items))


@router.get("/products", response_model=FuelProductListResponse)
def list_products(brand_id: int | None = Query(None, ge=1),
                  db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    rows = svc.list_products(db, brand_id)
    items = [FuelProductResponse.model_validate(p) for p in rows]
    for it, p in zip(items, rows):
        it.brand_name = p.brand.name if p.brand else None
    return FuelProductListResponse(items=items, total=len(items))


@router.get("/products/{product_id}/price", response_model=FuelPriceResponse)
def current_price(product_id: int, region: str = Query(...),
                  db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    p = svc.current_price(db, product_id, region)
    if not p:
        raise ApiError(404, "NOT_FOUND", "No current price for this product/region")
    return FuelPriceResponse.model_validate(p)


@router.get("/products/{product_id}/price/history", response_model=FuelPriceResponse)
def historical_price(product_id: int, region: str = Query(...),
                     on_date: date = Query(...),
                     db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    p = svc.price_on(db, product_id, region, on_date)
    if not p:
        raise ApiError(404, "NOT_FOUND", "No price on that date")
    return FuelPriceResponse.model_validate(p)
