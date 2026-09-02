"""Merchant service — normalization, aliases, resolution, ownership.

Merchant resolution flow:
    raw text -> normalize -> exact alias/canonical match -> optional confidence
Resolution NEVER mutates existing transactions; it only returns a candidate.
"""
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Merchant, MerchantAlias, MerchantType


class MerchantNotFound(Exception):
    pass


def normalize_merchant(text: str) -> str:
    """Lowercase, collapse whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def _visible_query(db: Session, user_id: int):
    """Global master merchants + the user's own custom merchants."""
    return db.query(Merchant).filter(
        (Merchant.user_id == user_id) | (Merchant.user_id.is_(None))
    )


def get_merchant(db: Session, merchant_id: int, user_id: int) -> Merchant | None:
    return _visible_query(db, user_id).filter(Merchant.id == merchant_id).first()


def get_merchant_or_raise(db: Session, merchant_id: int, user_id: int) -> Merchant:
    m = get_merchant(db, merchant_id, user_id)
    if not m:
        raise MerchantNotFound(f"Merchant {merchant_id} not found")
    return m


def get_own_merchant(db: Session, merchant_id: int, user_id: int) -> Merchant | None:
    """Strictly OWN merchant — used for update/delete so global rows stay safe."""
    return db.query(Merchant).filter(
        Merchant.id == merchant_id, Merchant.user_id == user_id
    ).first()


def list_merchants(db: Session, user_id: int, search: str | None = None,
                   category_id: int | None = None):
    q = _visible_query(db, user_id)
    if search:
        q = q.filter(
            (Merchant.canonical_name.ilike(f"%{search}%"))
            | (Merchant.normalized_name.ilike(f"%{search.lower()}%"))
            | (Merchant.display_name.ilike(f"%{search}%"))
        )
    if category_id:
        q = q.filter(Merchant.category_id == category_id)
    return q.order_by(Merchant.canonical_name).all()


def create_merchant(db: Session, *, user_id: int, canonical_name: str,
                    display_name: str | None = None, category_id: int | None = None,
                    merchant_type: MerchantType = MerchantType.OTHER,
                    source: str | None = None, source_url: str | None = None,
                    aliases: list[str] | None = None) -> Merchant:
    cname = canonical_name.strip()
    if not cname:
        raise ValueError("Merchant name required")
    m = Merchant(
        user_id=user_id, canonical_name=cname,
        display_name=(display_name or cname).strip(),
        normalized_name=normalize_merchant(cname),
        category_id=category_id, merchant_type=merchant_type,
        source=source, source_url=source_url,
    )
    db.add(m)
    db.flush()
    for alias in aliases or []:
        a = alias.strip()
        if a and normalize_merchant(a) != m.normalized_name:
            db.add(MerchantAlias(
                merchant_id=m.id, alias=a, normalized_alias=normalize_merchant(a),
                source=source,
            ))
    db.commit()
    db.refresh(m)
    return m


def update_merchant(db: Session, merchant_id: int, user_id: int, **fields) -> Merchant:
    m = get_own_merchant(db, merchant_id, user_id)
    if not m:
        raise MerchantNotFound(f"Merchant {merchant_id} not found")
    for key, value in fields.items():
        if key in ("canonical_name", "display_name") and value is not None:
            setattr(m, key, value.strip())
            if key == "canonical_name":
                m.normalized_name = normalize_merchant(value)
        elif key == "category_id":
            m.category_id = value
        elif key == "merchant_type":
            m.merchant_type = value
        elif key == "active":
            m.active = value
        elif key == "source":
            m.source = value
        elif key == "source_url":
            m.source_url = value
    db.commit()
    db.refresh(m)
    return m


def add_alias(db: Session, merchant_id: int, user_id: int, alias: str,
              source: str | None = None) -> MerchantAlias:
    m = get_merchant_or_raise(db, merchant_id, user_id)
    na = normalize_merchant(alias)
    if not na:
        raise ValueError("Alias required")
    existing = db.query(MerchantAlias).filter(
        MerchantAlias.merchant_id == m.id,
        MerchantAlias.normalized_alias == na,
    ).first()
    if existing:
        return existing
    a = MerchantAlias(merchant_id=m.id, alias=alias.strip(),
                      normalized_alias=na, source=source)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def delete_merchant(db: Session, merchant_id: int, user_id: int) -> None:
    m = get_own_merchant(db, merchant_id, user_id)
    if not m:
        raise MerchantNotFound(f"Merchant {merchant_id} not found")
    from app.models.models import Transaction
    used = db.query(Transaction.id).filter(
        Transaction.merchant_id == merchant_id
    ).first()
    if used:
        raise ValueError("Merchant still referenced by transactions")
    db.delete(m)
    db.commit()


def resolve_merchant(db: Session, text: str, user_id: int) -> dict | None:
    """Resolve raw text to a merchant. Returns None when unresolved.

    Precedence:
      1. exact normalized canonical match (user's + global)
      2. exact normalized alias match
    Ambiguity (multiple distinct matches) returns an 'ambiguous' marker so the
    caller can ask the user to confirm. Never mutates anything.
    """
    if not text:
        return None
    norm = normalize_merchant(text)
    if not norm:
        return None

    base = db.query(Merchant).filter(
        (Merchant.user_id == user_id) | (Merchant.user_id.is_(None))
    )

    canonical = base.filter(Merchant.normalized_name == norm).all()
    if len(canonical) == 1:
        return {
            "merchant_id": canonical[0].id,
            "matched_alias": norm,
            "confidence": 1.0,
            "match_method": "exact_canonical",
        }

    alias_rows = (
        db.query(MerchantAlias, Merchant)
        .join(Merchant, MerchantAlias.merchant_id == Merchant.id)
        .filter(
            MerchantAlias.normalized_alias == norm,
            (Merchant.user_id == user_id) | (Merchant.user_id.is_(None)),
        )
        .all()
    )
    if len(alias_rows) == 1:
        return {
            "merchant_id": alias_rows[0][1].id,
            "matched_alias": alias_rows[0][0].alias,
            "confidence": 0.95,
            "match_method": "exact_alias",
        }
    if len(alias_rows) > 1 or len(canonical) > 1:
        return {"ambiguous": True, "matches": [
            {"merchant_id": m.id, "canonical_name": m.canonical_name}
            for m in (canonical or [r[1] for r in alias_rows])
        ]}
    return None


def _to_response(m: Merchant) -> dict:
    return {
        "id": m.id,
        "canonical_name": m.canonical_name,
        "display_name": m.display_name,
        "category_id": m.category_id,
        "category_name": m.category.name if m.category else None,
        "merchant_type": m.merchant_type.value,
        "active": bool(m.active),
        "source": m.source,
        "source_url": m.source_url,
        "aliases": [a.alias for a in m.aliases],
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }

