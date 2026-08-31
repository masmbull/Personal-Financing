"""Savings goal service - deposits and withdrawals are internal movements.

Money moved into/out of goals is never counted as income or expense.
"""
from sqlalchemy.orm import Session

from app.models.models import SavingsGoal, SavingsGoalTransaction


class GoalNotFound(Exception):
    pass


class SavingsOperationError(ValueError):
    pass


def get_goal(db: Session, goal_id: int, user_id: int) -> SavingsGoal:
    goal = db.query(SavingsGoal).filter(
        SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id
    ).first()
    if not goal:
        raise GoalNotFound(f"Savings goal {goal_id} not found")
    return goal


def list_goals(db: Session, user_id: int, active_only: bool = True):
    query = db.query(SavingsGoal).filter(
        SavingsGoal.user_id == user_id
    ).order_by(SavingsGoal.created_at.desc())
    if active_only:
        query = query.filter(SavingsGoal.active == True)  # noqa: E712
    return query.all()


def to_response_dict(goal: SavingsGoal) -> dict:
    pct = (goal.current_amount * 100 / goal.target_amount
           if goal.target_amount > 0 else 0)
    return {
        "id": goal.id, "name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "progress_percentage": round(pct, 1),
        "icon": goal.icon, "color": goal.color,
        "notes": goal.notes, "active": bool(goal.active),
        "created_at": goal.created_at, "updated_at": goal.updated_at,
    }


def create_goal(db: Session, *, user_id: int, **fields) -> SavingsGoal:
    target = int(fields["target_amount"])
    if target <= 0:
        raise ValueError("Amount must be positive")
    goal = SavingsGoal(
        user_id=user_id,
        name=(fields["name"] or "").strip(),
        target_amount=target, current_amount=0,
        icon=(fields.get("icon") or "").strip() or None,
        color=fields.get("color"),
        notes=(fields.get("notes") or "").strip() or None,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, goal_id: int, user_id: int, fields: dict) -> SavingsGoal:
    goal = get_goal(db, goal_id, user_id)
    for key in ("name", "target_amount", "icon", "color", "notes", "active"):
        value = fields.get(key)
        if value is not None:
            setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return goal


def deposit(db: Session, goal_id: int, *, user_id: int, amount: int,
            related_account_id: int | None = None,
            notes: str | None = None) -> SavingsGoal:
    goal = get_goal(db, goal_id, user_id)
    amount = int(amount)
    if amount <= 0:
        raise SavingsOperationError("Amount must be positive")
    goal.current_amount += amount
    tx = SavingsGoalTransaction(
        user_id=user_id, goal_id=goal.id, amount=amount,
        notes=(notes or "").strip() or None,
        related_account_id=int(related_account_id) if related_account_id else None,
    )
    db.add(tx)
    db.commit()
    db.refresh(goal)
    return goal


def withdraw(db: Session, goal_id: int, *, user_id: int, amount: int,
             related_account_id: int | None = None,
             notes: str | None = None) -> SavingsGoal:
    goal = get_goal(db, goal_id, user_id)
    amount = int(amount)
    if amount <= 0:
        raise SavingsOperationError("Amount must be positive")
    if amount > goal.current_amount:
        raise SavingsOperationError("Withdrawal exceeds saved amount")
    goal.current_amount -= amount
    tx = SavingsGoalTransaction(
        user_id=user_id, goal_id=goal.id, amount=-amount,
        notes=(notes or "").strip() or None,
        related_account_id=int(related_account_id) if related_account_id else None,
    )
    db.add(tx)
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, goal_id: int, user_id: int) -> None:
    goal = get_goal(db, goal_id, user_id)
    db.delete(goal)
    db.commit()
