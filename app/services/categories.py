"""Category service - minimal CRUD + usage guard."""
from sqlalchemy.orm import Session

from app.models.models import Category, Transaction, TransactionType


class CategoryNotFound(Exception):
    pass


class CategoryInUse(Exception):
    """Category referenced by transactions/bills -> HTTP 409."""


def get_category(db: Session, category_id: int) -> Category | None:
    return db.query(Category).filter(Category.id == category_id).first()


def list_categories(db: Session, type: str | None = None):
    query = db.query(Category).order_by(Category.name)
    if type:
        query = query.filter(Category.type == TransactionType(type.upper()))
    return query.all()


def create_category(db: Session, *, name: str, type_: TransactionType,
                    group: str | None = None, icon: str | None = None) -> Category:
    cat = Category(name=name.strip(), type=type_, group=group,
                   icon=(icon or "").strip() or None, is_default=0)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, category_id: int, fields: dict) -> Category:
    cat = get_category(db, category_id)
    if not cat:
        raise CategoryNotFound(f"Category {category_id} not found")
    for key in ("name", "group", "icon"):
        value = fields.get(key)
        if value is not None:
            setattr(cat, key, value.strip() if isinstance(value, str) else value)
    if fields.get("type") is not None:
        cat.type = fields["type"]
    db.commit()
    db.refresh(cat)
    return cat


def delete_category(db: Session, category_id: int) -> None:
    from app.services.finance import has_transactions_for_category
    cat = get_category(db, category_id)
    if not cat:
        raise CategoryNotFound(f"Category {category_id} not found")
    if has_transactions_for_category(db, category_id):
        raise CategoryInUse(f"Category {category_id} is used by transactions")
    db.delete(cat)
    db.commit()
