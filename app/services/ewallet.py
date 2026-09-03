"""E-wallet / e-money provider master data.

Separate from FinancialInstitution: an e-wallet is a stored-value account held
at the operator, not a deposit account at a licensed bank. Global rows
(user_id=NULL) are seeded; users may READ/REFERENCE but not mutate.
"""
from sqlalchemy.orm import Session

from app.models.models import EWalletProvider


class ProviderNotFound(Exception):
    pass


def _visible_query(db: Session, user_id: int):
    return db.query(EWalletProvider).filter(
        (EWalletProvider.user_id == user_id) | (EWalletProvider.user_id.is_(None))
    )


def list_providers(db: Session, user_id: int, active_only: bool = True):
    q = _visible_query(db, user_id)
    if active_only:
        q = q.filter(EWalletProvider.active.is_(True))
    return q.order_by(EWalletProvider.short_name).all()


def get_provider(db: Session, provider_id: int, user_id: int) -> EWalletProvider | None:
    return _visible_query(db, user_id).filter(
        EWalletProvider.id == provider_id
    ).first()


def get_provider_or_raise(db: Session, provider_id: int, user_id: int) -> EWalletProvider:
    p = get_provider(db, provider_id, user_id)
    if not p:
        raise ProviderNotFound(f"Provider {provider_id} not found")
    return p


def get_own_provider(db: Session, provider_id: int, user_id: int) -> EWalletProvider | None:
    return db.query(EWalletProvider).filter(
        EWalletProvider.id == provider_id, EWalletProvider.user_id == user_id
    ).first()


def create_provider(db: Session, *, user_id: int, code: str, legal_name: str,
                    short_name: str, aliases: str | None = None,
                    operator_type: str | None = None, active: bool = True,
                    source: str | None = None, source_url: str | None = None,
                    notes: str | None = None, effective_from=None,
                    effective_until=None) -> EWalletProvider:
    code = code.strip()
    if not code:
        raise ValueError("Provider code required")
    p = EWalletProvider(
        user_id=user_id, code=code, legal_name=legal_name.strip(),
        short_name=short_name.strip(), aliases=aliases,
        operator_type=operator_type, active=active, source=source,
        source_url=source_url, notes=notes, effective_from=effective_from,
        effective_until=effective_until,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_provider(db: Session, provider_id: int, user_id: int, **fields) -> EWalletProvider:
    p = get_own_provider(db, provider_id, user_id)
    if not p:
        raise ProviderNotFound(f"Provider {provider_id} not found")
    for key, value in fields.items():
        if value is not None:
            setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return p


def delete_provider(db: Session, provider_id: int, user_id: int) -> None:
    p = get_own_provider(db, provider_id, user_id)
    if not p:
        raise ProviderNotFound(f"Provider {provider_id} not found")
    db.delete(p)
    db.commit()


def _to_response(p: EWalletProvider) -> dict:
    return {
        "id": p.id,
        "code": p.code,
        "legal_name": p.legal_name,
        "short_name": p.short_name,
        "aliases": p.aliases,
        "operator_type": p.operator_type,
        "active": bool(p.active),
        "source": p.source,
        "source_url": p.source_url,
        "verified_at": p.verified_at,
        "effective_from": p.effective_from,
        "effective_until": p.effective_until,
        "notes": p.notes,
    }
