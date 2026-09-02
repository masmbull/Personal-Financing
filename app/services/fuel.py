"""Fuel/BBM reference service — brands, products, historical price lookup.

Fuel prices are historical reference data. A transaction's amount is the
authoritative ledger; price_per_liter here is informational reference data.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models.models import FuelBrand, FuelPrice, FuelProduct


class FuelNotFound(Exception):
    pass


def list_brands(db: Session, active_only: bool = True):
    q = db.query(FuelBrand)
    if active_only:
        q = q.filter(FuelBrand.active.is_(True))
    return q.order_by(FuelBrand.name).all()


def get_brand(db: Session, brand_id: int) -> FuelBrand | None:
    return db.query(FuelBrand).filter(FuelBrand.id == brand_id).first()


def get_brand_or_raise(db: Session, brand_id: int) -> FuelBrand:
    b = get_brand(db, brand_id)
    if not b:
        raise FuelNotFound(f"Fuel brand {brand_id} not found")
    return b


def list_products(db: Session, brand_id: int | None = None, active_only: bool = True):
    q = db.query(FuelProduct)
    if brand_id:
        q = q.filter(FuelProduct.brand_id == brand_id)
    if active_only:
        q = q.filter(FuelProduct.active.is_(True))
    return q.order_by(FuelProduct.name).all()


def get_product(db: Session, product_id: int) -> FuelProduct | None:
    return db.query(FuelProduct).filter(FuelProduct.id == product_id).first()


def get_product_or_raise(db: Session, product_id: int) -> FuelProduct:
    p = get_product(db, product_id)
    if not p:
        raise FuelNotFound(f"Fuel product {product_id} not found")
    return p


def current_price(db: Session, product_id: int, region: str) -> dict | None:
    """The price effective today (or the newest active row with no until date)."""
    today = date.today()
    row = (
        db.query(FuelPrice)
        .filter(
            FuelPrice.product_id == product_id,
            FuelPrice.region == region,
            FuelPrice.effective_from <= today,
            (FuelPrice.effective_until.is_(None)) | (FuelPrice.effective_until >= today),
        )
        .order_by(FuelPrice.effective_from.desc())
        .first()
    )
    return _price_to_dict(row) if row else None


def price_on(db: Session, product_id: int, region: str, on_date: date) -> dict | None:
    """Historical price effective on a specific date."""
    row = (
        db.query(FuelPrice)
        .filter(
            FuelPrice.product_id == product_id,
            FuelPrice.region == region,
            FuelPrice.effective_from <= on_date,
            (FuelPrice.effective_until.is_(None)) | (FuelPrice.effective_until >= on_date),
        )
        .order_by(FuelPrice.effective_from.desc())
        .first()
    )
    return _price_to_dict(row) if row else None


def insert_price(db: Session, *, product_id: int, region: str,
                 price_per_liter: int, effective_from: date,
                 effective_until: date | None = None,
                 source: str | None = None, source_url: str | None = None
                 ) -> FuelPrice:
    get_product_or_raise(db, product_id)
    p = FuelPrice(
        product_id=product_id, region=region,
        price_per_liter=price_per_liter, effective_from=effective_from,
        effective_until=effective_until, source=source, source_url=source_url,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def list_prices(db: Session, product_id: int, region: str | None = None):
    q = db.query(FuelPrice).filter(FuelPrice.product_id == product_id)
    if region:
        q = q.filter(FuelPrice.region == region)
    return q.order_by(FuelPrice.effective_from).all()


def _price_to_dict(p: FuelPrice) -> dict:
    return {
        "id": p.id,
        "product_id": p.product_id,
        "region": p.region,
        "price_per_liter": p.price_per_liter,
        "currency": p.currency,
        "effective_from": p.effective_from,
        "effective_until": p.effective_until,
        "source": p.source,
        "source_url": p.source_url,
    }
