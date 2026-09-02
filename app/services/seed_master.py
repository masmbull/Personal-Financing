"""Seed master/reference data: payment methods, merchants, fuel.

All idempotent (match by natural key, never duplicate). Global rows have
user_id=NULL so ordinary users can never modify them.
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.models import (
    FuelBrand, FuelPrice, FuelProduct, Merchant, MerchantAlias,
    MerchantType, PaymentMethod, PaymentMethodType,
)

_IDR = "IDR"


def seed_payment_methods(db: Session) -> int:
    """Global Indonesian payment methods (user_id=NULL)."""
    rows = [
        ("Cash", PaymentMethodType.CASH),
        ("Bank Transfer", PaymentMethodType.BANK_TRANSFER),
        ("Virtual Account", PaymentMethodType.VIRTUAL_ACCOUNT),
        ("Debit Card", PaymentMethodType.DEBIT_CARD),
        ("Credit Card", PaymentMethodType.CREDIT_CARD),
        ("QRIS", PaymentMethodType.QRIS),
        ("E-Wallet", PaymentMethodType.EWALLET),
        ("Direct Debit", PaymentMethodType.DIRECT_DEBIT),
        ("Auto Debit", PaymentMethodType.AUTO_DEBIT),
        ("PayLater", PaymentMethodType.PAYLATER),
        ("Lainnya", PaymentMethodType.OTHER),
    ]
    created = 0
    for name, mtype in rows:
        existing = db.query(PaymentMethod).filter(
            PaymentMethod.name == name,
            PaymentMethod.user_id.is_(None),
        ).first()
        if not existing:
            db.add(PaymentMethod(
                user_id=None, name=name, method_type=mtype,
                source="Bank Indonesia / OJK", source_url=None,
                verified_at=datetime(2024, 1, 15), effective_from=date(2024, 1, 1),
            ))
            created += 1
    db.commit()
    return created


def seed_merchants(db: Session) -> int:
    """Common Indonesian merchant catalog (global, user_id=NULL)."""
    merchants = [
        ("Indomaret", ["INDOMRT", "Indomart"], MerchantType.RETAIL),
        ("Alfamart", ["ALFAMART", "Alfa"], MerchantType.RETAIL),
        ("Tokopedia", ["TOKOPEDIA", "Tokped"], MerchantType.MARKETPLACE),
        ("Shopee", ["SHOPEE"], MerchantType.MARKETPLACE),
        ("Gojek", ["GOJEK"], MerchantType.TRANSPORT),
        ("Grab", ["GRAB"], MerchantType.TRANSPORT),
        ("Telkomsel", ["TELKOMSEL"], MerchantType.TELECOM),
        ("Indosat", ["INDOSAT", "IM3"], MerchantType.TELECOM),
        ("DANA", ["DANA"], MerchantType.FINANCIAL),
        ("GoPay", ["GOPAY"], MerchantType.FINANCIAL),
        ("OVO", ["OVO"], MerchantType.FINANCIAL),
        ("Pertamina SPBU", ["SPBU", "PERTAMINA"], MerchantType.TRANSPORT),
    ]
    created = 0
    for canonical, aliases, mtype in merchants:
        existing = db.query(Merchant).filter(
            Merchant.canonical_name == canonical,
            Merchant.user_id.is_(None),
        ).first()
        if existing:
            continue
        m = Merchant(
            user_id=None, canonical_name=canonical,
            display_name=canonical,
            normalized_name=canonical.strip().lower(),
            merchant_type=mtype,
            source="Ekosistem Indonesia", verified_at=datetime(2024, 1, 15),
        )
        db.add(m)
        db.flush()
        for a in aliases:
            db.add(MerchantAlias(
                merchant_id=m.id, alias=a, normalized_alias=a.strip().lower(),
                source="Alias",
            ))
        created += 1
    db.commit()
    return created


def seed_fuel(db: Session) -> int:
    """Fuel brands, products, and historical prices."""
    def _brand(name):
        b = db.query(FuelBrand).filter_by(name=name).first()
        if not b:
            b = FuelBrand(name=name, country="ID",
                          source="Pertamina", verified_at=datetime(2024, 1, 15))
            db.add(b)
            db.flush()
        return b

    pertamina = _brand("Pertamina")

    def _product(brand, name, **kw):
        p = db.query(FuelProduct).filter(
            FuelProduct.brand_id == brand.id, FuelProduct.name == name
        ).first()
        if not p:
            p = FuelProduct(brand_id=brand.id, name=name, **kw)
            db.add(p)
            db.flush()
        return p

    pertalite = _product(pertamina, "Pertalite", product_code="PERTALITE",
                         fuel_type="gasoline", ron=90, specification="Euro 2")

    def _price(product, region, price, eff_from, until=None):
        existing = db.query(FuelPrice).filter(
            FuelPrice.product_id == product.id, FuelPrice.region == region,
            FuelPrice.effective_from == eff_from,
        ).first()
        if existing:
            return
        db.add(FuelPrice(
            product_id=product.id, region=region, price_per_liter=price,
            currency=_IDR, effective_from=eff_from, effective_until=until,
            source="Pertamina", verified_at=datetime(2024, 1, 15),
        ))

    _price(pertalite, "Jakarta", 10000, date(2026, 9, 1))
    db.commit()
    return 1


def seed_master_data(db: Session) -> int:
    """Seed all master/reference tables idempotently."""
    total = 0
    total += seed_payment_methods(db)
    total += seed_merchants(db)
    total += seed_fuel(db)
    return total
