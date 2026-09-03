from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.account import (
    AccountCreate, AccountListResponse, AccountResponse, AccountUpdate,
)
from app.services import accounts as accounts_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _out(acc) -> AccountResponse:
    return AccountResponse(
        id=acc.id, name=acc.name, type=acc.type,
        institution=acc.institution, account_number=acc.account_number,
        color=acc.color, icon=acc.icon,
        initial_balance=acc.initial_balance,
        current_balance=acc.current_balance,
        credit_limit=acc.credit_limit, statement_date=acc.statement_date,
        payment_due_day=acc.payment_due_day,
        interest_rate_pct=acc.interest_rate_pct, annual_fee=acc.annual_fee,
        card_network=acc.card_network, institution_id=acc.institution_id,
        available_credit=accounts_service.get_available_credit(acc),
        created_at=acc.created_at, updated_at=acc.updated_at,
    )


@router.get(
    "", response_model=AccountListResponse,
    summary="List accounts",
    description="All accounts with their calculated current balances.",
)
def list_accounts(db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    items = [_out(a) for a in accounts_service.list_accounts(db, user.id)]
    return AccountListResponse(items=items, total=len(items))


@router.post(
    "", response_model=AccountResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create an account",
    description="Creates an account; current_balance starts at initial_balance.",
    responses={201: {"description": "Created"}, 400: {"description": "Invalid input"}},
)
def create_account(payload: AccountCreate,
                   db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    acc = accounts_service.create_account(
        db, user_id=user.id, name=payload.name, type_=payload.type,
        initial_balance=payload.initial_balance, icon=payload.icon,
        institution=payload.institution, account_number=payload.account_number,
        color=payload.color,
        credit_limit=payload.credit_limit, statement_date=payload.statement_date,
        payment_due_day=payload.payment_due_day,
        interest_rate_pct=payload.interest_rate_pct, annual_fee=payload.annual_fee,
        card_network=payload.card_network, institution_id=payload.institution_id,
    )
    return _out(acc)


@router.get(
    "/{account_id}", response_model=AccountResponse,
    summary="Get one account",
    responses={404: {"description": "Account not found"}},
)
def get_account(account_id: int, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    return _out(accounts_service.get_account_or_raise(db, account_id, user.id))


@router.put(
    "/{account_id}", response_model=AccountResponse,
    summary="Update an account (partial)",
    description="Only provided fields are changed. Changing initial_balance "
                "recalculates current_balance.",
    responses={404: {"description": "Account not found"}},
)
def update_account(account_id: int, payload: AccountUpdate,
                   db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    acc = accounts_service.update_account(
        db, account_id, user.id, **payload.model_dump(exclude_unset=True)
    )
    return _out(acc)


@router.delete(
    "/{account_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete an account",
    responses={
        204: {"description": "Deleted"},
        404: {"description": "Account not found"},
        409: {"description": "Account still referenced by transactions"},
    },
)
def delete_account(account_id: int, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    accounts_service.delete_account(db, account_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)