from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.models.models import TransactionType
from app.schemas.transaction import (
    TransactionCreate, TransactionListResponse, TransactionResponse,
    TransactionUpdate,
)
from app.services import transactions as tx_service
from app.services.finance import create_transaction, delete_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get(
    "", response_model=TransactionListResponse,
    summary="List transactions",
    description="Filterable, paginated transaction feed. Filters combine with AND.",
)
def list_transactions(
    type: Optional[TransactionType] = Query(None, description="EXPENSE | INCOME | TRANSFER"),
    account_id: Optional[int] = Query(None, ge=1),
    category_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[date] = Query(None, description="Inclusive ISO date"),
    date_to: Optional[date] = Query(None, description="Inclusive ISO date"),
    merchant: Optional[str] = Query(None, description="Case-insensitive contains"),
    search: Optional[str] = Query(None, description="Matches description, merchant and notes"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    items, total, page, page_size = tx_service.list_transactions(
        db, user_id=user.id,
        type=type.value if type else None,
        account_id=account_id, category_id=category_id,
        date_from=date_from, date_to=date_to,
        merchant=merchant, search=search,
        page=page, page_size=page_size,
    )
    return TransactionListResponse(
        items=[TransactionResponse(**i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.post(
    "", response_model=TransactionResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a transaction",
    description=(
        "Records income or expense against one account and recalculates its "
        "balance. category_id is required for income/expense."
    ),
    responses={201: {"description": "Created"}, 400: {"description": "Invalid input"}},
)
def create_transaction_endpoint(payload: TransactionCreate,
                                db: Session = Depends(get_db),
                                user: CurrentUser = Depends(get_current_user)):
    try:
        tx = create_transaction(
            db=db, user_id=user.id,
            type=payload.type, amount=payload.amount,
            account_id=payload.account_id,
            category_id=payload.category_id,
            date_val=payload.date or date.today(),
            description=payload.description,
            merchant=payload.merchant, notes=payload.notes,
        )
    except ValueError as e:
        from app.api.errors import ApiError
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return TransactionResponse(**tx_service._to_response(tx))


@router.get(
    "/{transaction_id}", response_model=TransactionResponse,
    summary="Get one transaction",
    responses={404: {"description": "Not found"}},
)
def get_transaction(transaction_id: int, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    return TransactionResponse(**tx_service.get_transaction(db, transaction_id, user.id))


@router.put(
    "/{transaction_id}", response_model=TransactionResponse,
    summary="Update a transaction (partial)",
    description="Only provided fields change; balances are recalculated.",
    responses={404: {"description": "Not found"}, 400: {"description": "Invalid input"}},
)
def update_transaction(transaction_id: int, payload: TransactionUpdate,
                       db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    fields = payload.model_dump(exclude_unset=True)
    if "type" in fields and fields["type"] is not None:
        fields["type"] = fields["type"]
    return TransactionResponse(**tx_service.update_transaction(db, transaction_id, fields, user.id))


@router.delete(
    "/{transaction_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a transaction",
    responses={404: {"description": "Not found"}},
)
def delete_transaction_endpoint(transaction_id: int, db: Session = Depends(get_db),
                                user: CurrentUser = Depends(get_current_user)):
    tx_service.get_transaction(db, transaction_id, user.id)  # 404 when missing or not owned
    delete_transaction(db, transaction_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)