from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.models import DebtType
from app.schemas.debt import (
    DebtCreate, DebtListResponse, DebtPaymentCreate, DebtResponse, DebtUpdate,
)
from app.services import debts as debts_service

router = APIRouter(prefix="/debts", tags=["debts"])


def _payment_out(p) -> dict:
    return {
        "id": p.id, "amount": p.amount, "payment_date": p.payment_date,
        "notes": p.notes, "transaction_id": p.transaction_id,
        "created_at": p.created_at,
    }


def _debt_out(d) -> DebtResponse:
    return DebtResponse(
        id=d.id, type=d.type, person_name=d.person_name,
        person_contact=d.person_contact, description=d.description,
        principal_amount=d.principal_amount,
        remaining_amount=d.remaining_amount,
        interest_rate=d.interest_rate, start_date=d.start_date,
        due_date=d.due_date, installment_amount=d.installment_amount,
        installment_count=d.installment_count, status=d.status,
        related_account_id=d.related_account_id, notes=d.notes,
        payments=[_payment_out(p) for p in d.payments],
    )


@router.get(
    "", response_model=DebtListResponse,
    summary="List debts",
    description="PAYABLE = money you owe, RECEIVABLE = money owed to you. "
                "Overdue open items are flagged automatically.",
)
def list_debts(type: Optional[DebtType] = Query(None),
               db: Session = Depends(get_db)):
    items = [_debt_out(d) for d in debts_service.list_debts(db, type)]
    return DebtListResponse(items=items, total=len(items))


@router.post(
    "", response_model=DebtResponse, status_code=http_status.HTTP_201_CREATED,
    summary="Record a new debt",
    responses={400: {"description": "Invalid input"}},
)
def create_debt(payload: DebtCreate, db: Session = Depends(get_db)):
    debt = debts_service.create_debt(
        db, type=payload.type, person_name=payload.person_name,
        principal_amount=payload.principal_amount,
        description=payload.description or "",
        due_date=payload.due_date,
        installment_amount=payload.installment_amount,
        installment_count=payload.installment_count,
        interest_rate=payload.interest_rate,
        notes=payload.notes or "",
        person_contact=payload.person_contact or "",
        related_account_id=payload.related_account_id,
    )
    return _debt_out(debt)


@router.get(
    "/{debt_id}", response_model=DebtResponse,
    summary="Get one debt (with payment history)",
    responses={404: {"description": "Not found"}},
)
def get_debt(debt_id: int, db: Session = Depends(get_db)):
    return _debt_out(debts_service.get_debt(db, debt_id))


@router.put(
    "/{debt_id}", response_model=DebtResponse,
    summary="Update a debt (partial)",
    description="Editable metadata only; amounts are mutated via payments.",
    responses={404: {"description": "Not found"}},
)
def update_debt(debt_id: int, payload: DebtUpdate, db: Session = Depends(get_db)):
    debt = debts_service.update_debt(
        db, debt_id, payload.model_dump(exclude_unset=True)
    )
    return _debt_out(debt)


@router.delete(
    "/{debt_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a debt",
    responses={404: {"description": "Not found"}},
)
def delete_debt(debt_id: int, db: Session = Depends(get_db)):
    debts_service.delete_debt(db, debt_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post(
    "/{debt_id}/payments", response_model=DebtResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Pay a debt",
    description=(
        "Reduces remaining_amount and updates status "
        "(OPEN/PARTIALLY_PAID/PAID). When account_id is provided a real "
        "expense (PAYABLE) or income (RECEIVABLE) transaction is created so "
        "account balances stay correct."
    ),
    responses={
        201: {"description": "Payment recorded"},
        400: {"description": "Payment exceeds remaining amount or invalid"},
        404: {"description": "Debt not found"},
    },
)
def pay_debt(debt_id: int, payload: DebtPaymentCreate,
             db: Session = Depends(get_db)):
    from datetime import date
    debt, _payment = debts_service.pay_debt(
        db, debt_id, amount=payload.amount,
        account_id=payload.account_id,
        payment_date=payload.payment_date or date.today(),
        notes=payload.notes,
    )
    return _debt_out(debt)