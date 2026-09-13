"""Audit logging service.

Single entry point for recording security/activity events. Kept deliberately
small: just append a row. Consumers (routes) call ``record(...)`` after
performing a sensitive action.
"""
import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger("app.services.audit")


def record(
    db: Session,
    action: str,
    actor_user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    detail: Optional[dict | str] = None,
) -> AuditLog:
    """Append an audit row. ``detail`` may be a dict or a pre-serialised str.

    Never raises on bad input beyond a DB failure - audit logging must not be
    able to break the primary request path. A serialisation failure falls back
    to a safe repr string.
    """
    if isinstance(detail, dict):
        try:
            detail_str = json.dumps(detail, default=str, sort_keys=True)
        except (TypeError, ValueError):
            detail_str = repr(detail)
    else:
        detail_str = detail

    row = AuditLog(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        detail=detail_str,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "audit action=%s actor=%s target=%s", action, actor_user_id, target_user_id
    )
    return row


def list_events(
    db: Session,
    action: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    """Query audit rows (newest first). Used by the admin Audit Log page."""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if actor_user_id is not None:
        q = q.filter(AuditLog.actor_user_id == actor_user_id)
    if target_user_id is not None:
        q = q.filter(AuditLog.target_user_id == target_user_id)
    return (
        q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
