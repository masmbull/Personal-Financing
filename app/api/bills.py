from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas.bill import (
    BillCreate, BillListResponse, BillPayRequest, BillPaymentResponse,
    BillResponse, BillUpdate,
)
from app.services import bills as bills_service

router = APIRouter(prefix="/bills", tags=["bills"])


def _bill_out(bill) -> BillResponse:
    return BillResponse(
        id=bill.id, name=bill.name, amount=bill.amount,
        frequency=bill.frequency, category_id=bill.category_id,
        account_id=bill.account_id, due_day=bill.due_day,
        auto_create=bool(bill.auto_create), notes=bill.notes,
        active=bool(bill.active),
        next_due_date=bills_service.compute_next_due_date(bill),
        created_at=bill.created_at, updated_at=bill.updated_at,
    )


@router.get(
    "", response_model=BillListResponse,
    summary="List recurring bills",
    description="Each bill includes its calculated next_due_date.",
)
def list_bills(active_only: bool = Query(True),
               db: Session = Depends(get_db)):
    items = [_bill_out(b) for b in bills_service.list_bills(db, active_only)]
    return BillListResponse(items=items, total=len(items))


@router.post(
    "", response_model=BillResponse, status_code=http_status.HTTP_201_CREATED,
    summary="Create a recurring bill",
)
def create_bill(payload: BillCreate, db: Session = Depends(get_db)):
    bill = bills_service.create_bill(
        db, name=payload.name, amount=payload.amount,
        frequency=payload.frequency, category_id=payload.category_id,
        account_id=payload.account_id, due_day=payload.due_day,
        auto_create=payload.auto_create, notes=payload.notes or "",
    )
    return _bill_out(bill)


@router.get(
    "/{bill_id}", response_model=BillResponse,
    summary="Get one bill", responses={404: {"description": "Not found"}},
)
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    return _bill_out(bills_service.get_bill(db, bill_id))


@router.put(
    "/{bill_id}", response_model=BillResponse,
    summary="Update a bill (partial)",
    responses={404: {"description": "Not found"}},
)
def update_bill(bill_id: int, payload: BillUpdate, db: Session = Depends(get_db)):
    bill = bills_service.update_bill(
        db, bill_id, payload.model_dump(exclude_unset=True)
    )
    return _bill_out(bill)


@router.post(
    "/{bill_id}/pay", response_model=BillPaymentResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Pay a bill",
    description=(
        "Records a payment. When an account is resolved (explicit or the "
        "bill default) a real EXPENSE transaction is created; the response "
        "carries its transaction_id."
    ),
    responses={201: {"description": "Paid"}, 404: {"description": "Not found"}},
)
def pay_bill(bill_id: int, payload: BillPayRequest, db: Session = Depends(get_db)):
    _bill, payment = bills_service.pay_bill(
        db, bill_id, amount=payload.amount, account_id=payload.account_id,
        pay_date=payload.pay_date or date.today(),
    )
    return BillPaymentResponse(
        id=payment.id, bill_id=payment.bill_id, amount=payment.amount,
        paid_date=payment.paid_date, transaction_id=payment.transaction_id,
    )


@router.delete(
    "/{bill_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a bill",
    responses={404: {"description": "Not found"}},
)
def delete_bill(bill_id: int, db: Session = Depends(get_db)):
    bills_service.delete_bill(db, bill_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)