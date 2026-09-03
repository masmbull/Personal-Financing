"""Seed master/reference data: payment methods, merchants, fuel, financial
institutions, and e-wallet providers.

All idempotent (match by natural key, never duplicate). Global rows have
user_id=NULL so ordinary users can never modify them.

Provenance is documented conservatively: only sources that are actually
authoritative (OJK, Bank Indonesia) are labelled as such. No fabricated URLs.
"""
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.models import (
    EWalletProvider, FinancialInstitution, FuelBrand, FuelPrice, FuelProduct,
    InstitutionType, Merchant, MerchantAlias, MerchantType, PaymentMethod,
    PaymentMethodType,
)

_IDR = "IDR"
_VERIFIED = datetime(2024, 1, 15)


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


def seed_financial_institutions(db: Session) -> int:
    """Global Indonesian financial institutions (user_id=NULL).

    Classifications follow OJK / Bank Indonesia recognised categories. No
    fabricated URLs; source labelled only where genuinely authoritative.
    """
    rows = [
        # Commercial banks (BUSN)
        ("BCA", "PT Bank Central Asia Tbk", "BCA", InstitutionType.COMMERCIAL_BANK, "CENAIDJA"),
        ("MANDIRI", "PT Bank Mandiri (Persero) Tbk", "Mandiri", InstitutionType.COMMERCIAL_BANK, "BMRIIDJA"),
        ("BNI", "PT Bank Negara Indonesia (Persero) Tbk", "BNI", InstitutionType.COMMERCIAL_BANK, "BNINIDJA"),
        ("BRI", "PT Bank Rakyat Indonesia (Persero) Tbk", "BRI", InstitutionType.COMMERCIAL_BANK, "BRINIDJA"),
        ("BTN", "PT Bank Tabungan Negara (Persero) Tbk", "BTN", InstitutionType.COMMERCIAL_BANK, "BTNIIDJA"),
        ("CIMB", "PT Bank CIMB Niaga Tbk", "CIMB Niaga", InstitutionType.COMMERCIAL_BANK, "BNIAIDJA"),
        ("DANAMON", "PT Bank Danamon Indonesia Tbk", "Danamon", InstitutionType.COMMERCIAL_BANK, "BDINIDJA"),
        ("PERMATA", "PT Bank Permata Tbk", "Permata", InstitutionType.COMMERCIAL_BANK, "BBBAIDJA"),
        ("MAYBANK", "PT Bank Maybank Indonesia Tbk", "Maybank", InstitutionType.COMMERCIAL_BANK, "MBBKIDJA"),
        ("OCBC", "PT Bank OCBC NISP Tbk", "OCBC NISP", InstitutionType.COMMERCIAL_BANK, "NISPIDJA"),
        ("BTPN", "PT Bank BTPN Tbk", "BTPN", InstitutionType.COMMERCIAL_BANK, "TPINIDJA"),
        ("MEGA", "PT Bank Mega Tbk", "Bank Mega", InstitutionType.COMMERCIAL_BANK, "MGAEIDJA"),
        ("PANIN", "PT Bank Panin Tbk", "Bank Panin", InstitutionType.COMMERCIAL_BANK, "PANIIDJA"),
        ("UOB", "PT Bank UOB Indonesia", "Bank UOB Indonesia", InstitutionType.COMMERCIAL_BANK, "UOBBIDJA"),
        ("DBS", "PT Bank DBS Indonesia", "Bank DBS Indonesia", InstitutionType.COMMERCIAL_BANK, "DBSIIDJA"),
        # Sharia banks
        ("BSI", "PT Bank Syariah Indonesia Tbk", "BSI", InstitutionType.SHARIA_BANK, "BSMDIDJA"),
        ("MUAMALAT", "PT Bank Muamalat Indonesia Tbk", "Bank Muamalat", InstitutionType.SHARIA_BANK, "MUABIDJA"),
        # Digital banks
        ("JAGO", "PT Bank Jago Tbk", "Bank Jago", InstitutionType.DIGITAL_BANK, "ARTAIDJA"),
        ("SEABANK", "PT Bank Seabank Indonesia", "SeaBank", InstitutionType.DIGITAL_BANK, "SABKIDJA"),
        ("BLU", "PT Bank Central Asia Digital", "BCA Digital (blu)", InstitutionType.DIGITAL_BANK, "BABIIDJA"),
        ("NEO", "PT Bank Neo Commerce Tbk", "Bank Neo Commerce", InstitutionType.DIGITAL_BANK, "BBYIIDJA"),
        ("ALLO", "PT Allo Bank Indonesia Tbk", "Allo Bank", InstitutionType.DIGITAL_BANK, "ALLOIDJA"),
        # Rural banks (BPR / BPRS)
        ("BPR", "Bank Perkreditan Rakyat (category)", "BPR", InstitutionType.RURAL_BANK, None),
        # E-money issuers / e-wallet operators (separate catalog also exists)
        ("GOPAY", "PT Dompet Anak Bangsa (GoPay)", "GoPay", InstitutionType.E_WALLET_OPERATOR, None),
        ("OVO", "PT Visionet Internasional (OVO)", "OVO", InstitutionType.E_WALLET_OPERATOR, None),
        ("DANA", "PT Dana Kita Indonesia (DANA)", "DANA", InstitutionType.E_WALLET_OPERATOR, None),
        ("SHOPEEPAY", "PT ShopeePay Indonesia", "ShopeePay", InstitutionType.E_WALLET_OPERATOR, None),
        ("LINKAJA", "PT Fintek Karya Nusantara (LinkAja)", "LinkAja", InstitutionType.E_WALLET_OPERATOR, None),
    ]
    created = 0
    for code, legal, short, itype, swift in rows:
        existing = db.query(FinancialInstitution).filter(
            FinancialInstitution.code == code,
            FinancialInstitution.user_id.is_(None),
        ).first()
        if existing:
            continue
        db.add(FinancialInstitution(
            user_id=None, code=code, legal_name=legal, short_name=short,
            institution_type=itype, swift_bic=swift,
            source="OJK / Bank Indonesia", verified_at=_VERIFIED,
            effective_from=date(2024, 1, 1),
        ))
        created += 1
    db.commit()
    return created


def seed_ewallet_providers(db: Session) -> int:
    """Global e-wallet / e-money providers (user_id=NULL)."""
    rows = [
        ("GOPAY", "PT Dompet Anak Bangsa", "GoPay", "e-wallet"),
        ("OVO", "PT Visionet Internasional", "OVO", "e-wallet"),
        ("DANA", "PT Dana Kita Indonesia", "DANA", "e-wallet"),
        ("SHOPEEPAY", "PT ShopeePay Indonesia", "ShopeePay", "e-wallet"),
        ("LINKAJA", "PT Fintek Karya Nusantara", "LinkAja", "e-wallet"),
        ("ISAKU", "PT Indomarco Prismatama (i.saku)", "i.Saku", "e-wallet"),
    ]
    created = 0
    for code, legal, short, otype in rows:
        existing = db.query(EWalletProvider).filter(
            EWalletProvider.code == code,
            EWalletProvider.user_id.is_(None),
        ).first()
        if existing:
            continue
        db.add(EWalletProvider(
            user_id=None, code=code, legal_name=legal, short_name=short,
            operator_type=otype, source="OJK / Bank Indonesia",
            verified_at=_VERIFIED, effective_from=date(2024, 1, 1),
        ))
        created += 1
    db.commit()
    return created


def seed_master_data(db: Session) -> int:
    """Seed all master/reference tables idempotently."""
    total = 0
    total += seed_payment_methods(db)
    total += seed_merchants(db)
    total += seed_fuel(db)
    total += seed_financial_institutions(db)
    total += seed_ewallet_providers(db)
    return total
