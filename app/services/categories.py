"""Category service - minimal CRUD + usage guard + optional hierarchy."""
from sqlalchemy.orm import Session, selectinload

from app.models.models import Category, Transaction, TransactionType


class CategoryNotFound(Exception):
    pass


class CategoryInUse(Exception):
    """Category referenced by transactions/bills -> HTTP 409."""


class CategoryInvalidParent(Exception):
    """parent_id points to a category of a different type or is an ancestor."""


def get_category(db: Session, category_id: int) -> Category | None:
    return db.query(Category).filter(Category.id == category_id).first()


def list_categories(db: Session, type: str | None = None):
    query = db.query(Category).options(
        selectinload(Category.children)
    ).order_by(Category.name)
    if type:
        query = query.filter(Category.type == TransactionType(type.upper()))
    return query.all()


def _validate_parent(db: Session, parent_id: int | None,
                     tx_type: TransactionType) -> Category | None:
    """Return parent or None.  Raises CategoryInvalidParent on mismatch."""
    if parent_id is None:
        return None
    parent = get_category(db, parent_id)
    if parent is None:
        raise CategoryInvalidParent(f"Parent category {parent_id} not found")
    if parent.type != tx_type:
        raise CategoryInvalidParent(
            f"Parent category type {parent.type} != {tx_type}")
    return parent


def _cycle_check(db: Session, category_id: int, parent_id: int) -> None:
    """Reject assigning to an ancestor (cycle)."""
    cur = parent_id
    seen = set()
    while cur is not None:
        if cur == category_id:
            raise CategoryInvalidParent("Cycle detected in category hierarchy")
        if cur in seen:
            return
        seen.add(cur)
        p = get_category(db, cur)
        if p is None or p.parent_id is None:
            return
        cur = p.parent_id


def create_category(db: Session, *, name: str, type_: TransactionType,
                    group: str | None = None, icon: str | None = None,
                    parent_id: int | None = None) -> Category:
    parent = _validate_parent(db, parent_id, type_)
    if parent is not None and parent.type != type_:
        raise CategoryInvalidParent(
            f"Parent category type {parent.type} != {type_}")
    cat = Category(name=name.strip(), type=type_, group=group,
                   icon=(icon or "").strip() or None, is_default=0,
                   parent_id=parent.id if parent else None)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, category_id: int, fields: dict) -> Category:
    cat = get_category(db, category_id)
    if not cat:
        raise CategoryNotFound(f"Category {category_id} not found")
    if "type" in fields and fields["type"] is not None:
        new_type = fields["type"]
        if cat.parent_id is not None:
            parent = get_category(db, cat.parent_id)
            if parent is not None and parent.type != new_type:
                raise CategoryInvalidParent("New type differs from parent type")
        cat.type = new_type
    if "parent_id" in fields:
        new_parent_id = fields["parent_id"]
        if new_parent_id is not None:
            _cycle_check(db, category_id, new_parent_id)
            _validate_parent(db, new_parent_id, cat.type)
        cat.parent_id = new_parent_id
    for key in ("name", "group", "icon"):
        value = fields.get(key)
        if value is not None:
            setattr(cat, key, value.strip() if isinstance(value, str) else value)
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


def tree(db: Session, tx_type: str | None = None) -> list[dict]:
    """Return nested category tree (roots first)."""
    query = db.query(Category).order_by(Category.name)
    if tx_type:
        query = query.filter(Category.type == TransactionType(tx_type.upper()))
    cats = query.all()
    by_id = {c.id: {"id": c.id, "name": c.name, "type": c.type.value,
                    "icon": c.icon, "group": c.group, "slug": c.slug,
                    "children": []} for c in cats}
    roots: list[dict] = []
    for c in cats:
        node = by_id[c.id]
        if c.parent_id is None or c.parent_id not in by_id:
            roots.append(node)
        else:
            by_id[c.parent_id]["children"].append(node)
    return roots

