"""Financial institution master data — Indonesian banks / licensed institutions.

Global rows (user_id=NULL) are seeded from authoritative OJK/Bank Indonesia
classifications. Users may READ and REFERENCE (Account.institution_id) but may
NOT modify or delete global master rows.
"""
from sqlalchemy.orm import Session

from app.models.models import FinancialInstitution, InstitutionType


class InstitutionNotFound(Exception):
    pass


def _visible_query(db: Session, user_id: int):
    """Global master institutions + the user's own custom institutions."""
    return db.query(FinancialInstitution).filter(
        (FinancialInstitution.user_id == user_id)
        | (FinancialInstitution.user_id.is_(None))
    )


def list_institutions(db: Session, user_id: int, active_only: bool = True,
                      institution_type: InstitutionType | None = None):
    q = _visible_query(db, user_id)
    if active_only:
        q = q.filter(FinancialInstitution.active.is_(True))
    if institution_type:
        q = q.filter(FinancialInstitution.institution_type == institution_type)
    return q.order_by(FinancialInstitution.short_name).all()


def get_institution(db: Session, institution_id: int, user_id: int) -> FinancialInstitution | None:
    return _visible_query(db, user_id).filter(
        FinancialInstitution.id == institution_id
    ).first()


def get_institution_or_raise(db: Session, institution_id: int, user_id: int) -> FinancialInstitution:
    inst = get_institution(db, institution_id, user_id)
    if not inst:
        raise InstitutionNotFound(f"Institution {institution_id} not found")
    return inst


def get_own_institution(db: Session, institution_id: int, user_id: int) -> FinancialInstitution | None:
    """Strictly OWN institution — used for update/delete so global rows stay safe."""
    return db.query(FinancialInstitution).filter(
        FinancialInstitution.id == institution_id,
        FinancialInstitution.user_id == user_id,
    ).first()


def create_institution(db: Session, *, user_id: int, code: str, legal_name: str,
                       short_name: str, institution_type: InstitutionType,
                       aliases: str | None = None, swift_bic: str | None = None,
                       active: bool = True, source: str | None = None,
                       source_url: str | None = None, notes: str | None = None,
                       effective_from=None, effective_until=None) -> FinancialInstitution:
    code = code.strip()
    if not code:
        raise ValueError("Institution code required")
    inst = FinancialInstitution(
        user_id=user_id, code=code, legal_name=legal_name.strip(),
        short_name=short_name.strip(), institution_type=institution_type,
        aliases=aliases, swift_bic=swift_bic, active=active, source=source,
        source_url=source_url, notes=notes, effective_from=effective_from,
        effective_until=effective_until,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def update_institution(db: Session, institution_id: int, user_id: int, **fields) -> FinancialInstitution:
    inst = get_own_institution(db, institution_id, user_id)
    if not inst:
        raise InstitutionNotFound(f"Institution {institution_id} not found")
    for key, value in fields.items():
        if value is not None:
            setattr(inst, key, value)
    db.commit()
    db.refresh(inst)
    return inst


def delete_institution(db: Session, institution_id: int, user_id: int) -> None:
    inst = get_own_institution(db, institution_id, user_id)
    if not inst:
        raise InstitutionNotFound(f"Institution {institution_id} not found")
    db.delete(inst)
    db.commit()


def _to_response(inst: FinancialInstitution) -> dict:
    return {
        "id": inst.id,
        "code": inst.code,
        "legal_name": inst.legal_name,
        "short_name": inst.short_name,
        "aliases": inst.aliases,
        "institution_type": inst.institution_type.value,
        "swift_bic": inst.swift_bic,
        "active": bool(inst.active),
        "source": inst.source,
        "source_url": inst.source_url,
        "verified_at": inst.verified_at,
        "effective_from": inst.effective_from,
        "effective_until": inst.effective_until,
        "notes": inst.notes,
    }
