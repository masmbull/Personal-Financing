"""Admin API routes - user management and system stats.

All endpoints require admin access (AdminDep dependency).
"""
from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import require_admin, CurrentUser
from app.database.db import get_db
from app.models.models import User
from app.services import users as users_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", summary="List all users (admin only)")
def list_users(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    users = users_service.list_users(db)
    return {
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "is_active": bool(u.is_active),
                "is_admin": bool(u.is_admin),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": len(users),
    }


@router.get("/users/{user_id}", summary="Get user details (admin only)")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    user = users_service.get_by_id(db, user_id)
    if user is None:
        return Response(status_code=http_status.HTTP_404_NOT_FOUND)
    return {
        "id": user.id,
        "username": user.username,
        "is_active": bool(user.is_active),
        "is_admin": bool(user.is_admin),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.put("/users/{user_id}/admin", summary="Promote/demote user admin status")
def set_admin(
    user_id: int,
    is_admin: bool,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    if user_id == admin.id:
        return Response(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            content="Cannot change your own admin status",
        )
    user = users_service.set_admin(db, user_id, is_admin)
    if user is None:
        return Response(status_code=http_status.HTTP_404_NOT_FOUND)
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": bool(user.is_admin),
    }


@router.post("/users/{user_id}/make-admin", summary="Promote a user to admin")
def make_admin(
    user_id: int,
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    """Convenience endpoint: grant admin role to another user."""
    if user_id == admin.id:
        return Response(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            content="Cannot change your own admin status",
        )
    user = users_service.set_admin(db, user_id, True)
    if user is None:
        return Response(status_code=http_status.HTTP_404_NOT_FOUND)
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": bool(user.is_admin),
    }


@router.get("/stats", summary="System statistics (admin only)")
def stats(
    db: Session = Depends(get_db),
    admin: CurrentUser = Depends(require_admin),
):
    from app.models.models import Account, Transaction, Debt, Bill, SavingsGoal, Budget

    return {
        "total_users": db.query(User).count(),
        "admin_count": db.query(User).filter(User.is_admin == 1).count(),
        "total_accounts": db.query(Account).count(),
        "total_transactions": db.query(Transaction).count(),
        "total_debts": db.query(Debt).count(),
        "total_bills": db.query(Bill).count(),
        "total_savings_goals": db.query(SavingsGoal).count(),
        "total_budgets": db.query(Budget).count(),
    }