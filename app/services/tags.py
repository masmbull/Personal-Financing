"""Tags service — CRUD + attach/detach to transactions."""
from sqlalchemy.orm import Session

from app.models.models import Tag, TransactionTag


class TagNotFound(Exception):
    pass


def list_tags(db: Session, user_id: int) -> list[dict]:
    rows = db.query(Tag).filter(Tag.user_id == user_id).order_by(Tag.name).all()
    return [{"id": t.id, "name": t.name, "color": t.color} for t in rows]


def create_tag(db: Session, user_id: int, name: str,
               color: str | None = None) -> dict:
    name = (name or "").strip()[:50]
    if not name:
        raise ValueError("Tag name is required")
    existing = db.query(Tag).filter(
        Tag.user_id == user_id, Tag.name == name
    ).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "color": existing.color}
    tag = Tag(user_id=user_id, name=name, color=color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


def delete_tag(db: Session, tag_id: int, user_id: int) -> None:
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == user_id).first()
    if not tag:
        raise TagNotFound(f"Tag {tag_id} not found")
    db.query(TransactionTag).filter(TransactionTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()


def attach_tags(db: Session, transaction_id: int, tag_ids: list[int],
                user_id: int) -> None:
    """Replace all tags on a transaction (idempotent)."""
    db.query(TransactionTag).filter(
        TransactionTag.transaction_id == transaction_id
    ).delete()
    for tid in tag_ids:
        tag = db.query(Tag).filter(Tag.id == tid, Tag.user_id == user_id).first()
        if tag:
            db.add(TransactionTag(transaction_id=transaction_id, tag_id=tid))
    db.commit()


def tags_for_transaction(db: Session, transaction_id: int) -> list[dict]:
    rows = (
        db.query(Tag)
        .join(TransactionTag, TransactionTag.tag_id == Tag.id)
        .filter(TransactionTag.transaction_id == transaction_id)
        .order_by(Tag.name)
        .all()
    )
    return [{"id": t.id, "name": t.name, "color": t.color} for t in rows]


def tags_for_transactions(db: Session, transaction_ids: list[int],
                          user_id: int) -> dict[int, list[dict]]:
    """Bulk-fetch tags for a list of transaction IDs. Returns {tx_id: [tag,...]}."""
    if not transaction_ids:
        return {}
    rows = (
        db.query(TransactionTag.transaction_id, Tag.id, Tag.name, Tag.color)
        .join(Tag, TransactionTag.tag_id == Tag.id)
        .filter(TransactionTag.transaction_id.in_(transaction_ids),
                Tag.user_id == user_id)
        .all()
    )
    result: dict[int, list[dict]] = {tid: [] for tid in transaction_ids}
    for tx_id, tid, name, color in rows:
        result[tx_id].append({"id": tid, "name": name, "color": color})
    return result
