from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.savings import (
    SavingsGoalCreate, SavingsGoalListResponse, SavingsGoalResponse,
    SavingsGoalUpdate, SavingsOperationRequest,
)
from app.services import savings as savings_service

router = APIRouter(prefix="/savings", tags=["savings"])


def _out(goal) -> SavingsGoalResponse:
    d = savings_service.to_response_dict(goal)
    return SavingsGoalResponse(**d)


@router.get(
    "", response_model=SavingsGoalListResponse,
    summary="List savings goals",
)
def list_goals(active_only: bool = True, db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    items = [_out(g) for g in savings_service.list_goals(db, user.id, active_only)]
    return SavingsGoalListResponse(items=items, total=len(items))


@router.post(
    "", response_model=SavingsGoalResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a savings goal",
)
def create_goal(payload: SavingsGoalCreate, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    goal = savings_service.create_goal(
        db, user_id=user.id, name=payload.name, target_amount=payload.target_amount,
        icon=payload.icon, color=payload.color, notes=payload.notes or "",
    )
    return _out(goal)


@router.get(
    "/{goal_id}", response_model=SavingsGoalResponse,
    summary="Get one goal with progress",
    responses={404: {"description": "Not found"}},
)
def get_goal(goal_id: int, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    return _out(savings_service.get_goal(db, goal_id, user.id))


@router.put(
    "/{goal_id}", response_model=SavingsGoalResponse,
    summary="Update a goal (partial)",
    responses={404: {"description": "Not found"}},
)
def update_goal(goal_id: int, payload: SavingsGoalUpdate,
                db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    goal = savings_service.update_goal(
        db, goal_id, user.id, payload.model_dump(exclude_unset=True)
    )
    return _out(goal)


@router.delete(
    "/{goal_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a goal",
    responses={404: {"description": "Not found"}},
)
def delete_goal(goal_id: int, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    savings_service.delete_goal(db, goal_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post(
    "/{goal_id}/deposit", response_model=SavingsGoalResponse,
    summary="Deposit into a goal",
    description=(
        "Increases the saved amount. This is an internal allocation - it is "
        "never counted as income or expense."
    ),
    responses={400: {"description": "Invalid amount"}, 404: {"description": "Not found"}},
)
def deposit(goal_id: int, payload: SavingsOperationRequest,
            db: Session = Depends(get_db),
            user: CurrentUser = Depends(get_current_user)):
    goal = savings_service.deposit(
        db, goal_id, user_id=user.id, amount=payload.amount,
        related_account_id=payload.related_account_id, notes=payload.notes,
    )
    return _out(goal)


@router.post(
    "/{goal_id}/withdraw", response_model=SavingsGoalResponse,
    summary="Withdraw from a goal",
    description="Decreases the saved amount; cannot exceed what is saved.",
    responses={400: {"description": "Exceeds saved amount"}, 404: {"description": "Not found"}},
)
def withdraw(goal_id: int, payload: SavingsOperationRequest,
             db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    goal = savings_service.withdraw(
        db, goal_id, user_id=user.id, amount=payload.amount,
        related_account_id=payload.related_account_id, notes=payload.notes,
    )
    return _out(goal)