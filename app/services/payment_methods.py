"""PaymentMethod service — global seed + per-user customs, ownership-scoped."""
from sqlalchemy.orm import Session

from app.models.models import PaymentMethod, PaymentMethodType


class PaymentMethodNotFound(Exception):
    pass


def _visible_query(db: Session, user_id: int):
    return db.query(PaymentMethod).filter(
        (PaymentMethod.user_id == user_id) | (PaymentMethod.user_id.is_(None))
    )


def list_payment_methods(db: Session, user_id: int,
                         method_type: PaymentMethodType | None = None):
    q = _visible_query(db, user_id)
    if method_type:
        q = q.filter(PaymentMethod.method_type == method_type)
    return q.order_by(PaymentMethod.name).all()


def get_payment_method(db: Session, pm_id: int, user_id: int) -> PaymentMethod | None:
    return _visible_query(db, user_id).filter(PaymentMethod.id == pm_id).first()


def get_payment_method_or_raise(db: Session, pm_id: int, user_id: int) -> PaymentMethod:
    pm = get_payment_method(db, pm_id, user_id)
    if not pm:
        raise PaymentMethodNotFound(f"Payment method {pm_id} not found")
    return pm


def get_own_payment_method(db: Session, pm_id: int, user_id: int):
    return db.query(PaymentMethod).filter(
        PaymentMethod.id == pm_id, PaymentMethod.user_id == user_id
    ).first()


def create_payment_method(db: Session, *, user_id: int, name: str,
                          method_type: PaymentMethodType,
                          source: str | None = None,
                          source_url: str | None = None,
                          notes: str | None = None) -> PaymentMethod:
    if not name or not name.strip():
        raise ValueError("Payment method name required")
    pm = PaymentMethod(user_id=user_id, name=name.strip(),
                       method_type=method_type, source=source,
                       source_url=source_url, notes=notes)
    db.add(pm)
    db.commit()
    db.refresh(pm)
    return pm


def update_payment_method(db: Session, pm_id: int, user_id: int, **fields) -> PaymentMethod:
    pm = get_own_payment_method(db, pm_id, user_id)
    if not pm:
        raise PaymentMethodNotFound(f"Payment method {pm_id} not found")
    for key, value in fields.items():
        if value is not None and key in ("name", "method_type", "active",
                                         "source", "source_url", "notes"):
            if key == "name":
                value = value.strip()
            setattr(pm, key, value)
    db.commit()
    db.refresh(pm)
    return pm


def delete_payment_method(db: Session, pm_id: int, user_id: int) -> None:
    pm = get_own_payment_method(db, pm_id, user_id)
    if not pm:
        raise PaymentMethodNotFound(f"Payment method {pm_id} not found")
    from app.models.models import Transaction
    if db.query(Transaction.id).filter(Transaction.payment_method_id == pm_id).first():
        raise ValueError("Payment method still referenced by transactions")
    db.delete(pm)
    db.commit()


def _to_response(pm: PaymentMethod) -> dict:
    return {
        "id": pm.id,
        "name": pm.name,
        "method_type": pm.method_type.value,
        "active": bool(pm.active),
        "source": pm.source,
        "source_url": pm.source_url,
        "notes": pm.notes,
        "created_at": pm.created_at,
        "updated_at": pm.updated_at,
    }
