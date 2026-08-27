"""Investment service."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.models import Investment


class InvestmentNotFound(Exception):
    pass


INVESTMENT_TYPES = [
    "Saham", "Reksadana", "Emas", "Crypto", "Deposit", "Obligasi", "Lainnya",
]


def get_investment(db: Session, inv_id: int) -> Investment:
    inv = db.query(Investment).filter(Investment.id == inv_id).first()
    if not inv:
        raise InvestmentNotFound(f"Investment {inv_id} not found")
    return inv


def list_investments(db: Session):
    return db.query(Investment).order_by(Investment.name).all()


def to_response_dict(inv: Investment) -> dict:
    gain = inv.current_value - inv.amount_invested
    pct = round(gain * 100 / inv.amount_invested, 2) if inv.amount_invested > 0 else 0.0
    return {
        "id": inv.id, "name": inv.name,
        "investment_type": inv.investment_type,
        "amount_invested": inv.amount_invested,
        "current_value": inv.current_value,
        "purchase_date": inv.purchase_date,
        "icon": inv.icon, "notes": inv.notes,
        "gain_loss": gain, "return_percentage": pct,
        "created_at": inv.created_at, "updated_at": inv.updated_at,
    }


def create_investment(db: Session, **fields) -> Investment:
    invested = int(fields["amount_invested"])
    current = int(fields["current_value"])
    if invested <= 0:
        raise ValueError("Amount must be positive")
    inv = Investment(
        name=(fields["name"] or "").strip(),
        investment_type=fields["investment_type"],
        amount_invested=invested, current_value=current,
        purchase_date=fields.get("purchase_date"),
        icon=(fields.get("icon") or "").strip() or None,
        notes=(fields.get("notes") or "").strip() or None,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def update_investment(db: Session, inv_id: int, fields: dict) -> Investment:
    inv = get_investment(db, inv_id)
    for key in ("name", "investment_type", "amount_invested", "current_value",
                "purchase_date", "icon", "notes"):
        value = fields.get(key)
        if value is not None:
            setattr(inv, key, value)
    db.commit()
    db.refresh(inv)
    return inv


def delete_investment(db: Session, inv_id: int) -> None:
    inv = get_investment(db, inv_id)
    db.delete(inv)
    db.commit()


def totals(db: Session) -> dict:
    items = [to_response_dict(i) for i in list_investments(db)]
    return {
        "items": items,
        "total_invested": sum(i["amount_invested"] for i in items),
        "total_current_value": sum(i["current_value"] for i in items),
        "total_gain_loss": sum(i["gain_loss"] for i in items),
    }
