"""Audit log model - append-only security/activity trail.

Records every sensitive action (login, logout, password change, admin
privilege changes, impersonation, etc). Rows are never updated or deleted
by normal code; they form the system of record for "who did what, when".
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index

from app.database.db import Base
from app.models.models import _utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    # Actor: who performed the action. NULL for system actions.
    actor_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    # Target: the user/entity the action affected (may differ from actor,
    # e.g. admin resetting another user's password).
    target_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    action = Column(String(64), nullable=False, index=True)
    entity_type = Column(String(32), nullable=True)
    entity_id = Column(Integer, nullable=True)
    ip_address = Column(String(64), nullable=True)
    detail = Column(Text, nullable=True)  # JSON string of relevant context
    created_at = Column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_created_action", "created_at", "action"),
    )
