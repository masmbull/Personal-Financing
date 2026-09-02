from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.bill import (
    BillCreate, BillListResponse, BillOccurrenceResponse, BillPayRequest,
    BillPaymentResponse, BillResponse, BillUpdate,
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
               db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    items = [_bill_out(b) for b in bills_service.list_bills(db, user.id, active_only)]
    return BillListResponse(items=items, total=len(items))


@router.post(
    "", response_model=BillResponse, status_code=http_status.HTTP_201_CREATED,
    summary="Create a recurring bill",
)
def create_bill(payload: BillCreate, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    bill = bills_service.create_bill(
        db, user_id=user.id, name=payload.name, amount=payload.amount,
        frequency=payload.frequency, category_id=payload.category_id,
        account_id=payload.account_id, due_day=payload.due_day,
        auto_create=payload.auto_create, notes=payload.notes or "",
    )
    return _bill_out(bill)


@router.get(
    "/{bill_id}", response_model=BillResponse,
    summary="Get one bill", responses={404: {"description": "Not found"}},
)
def get_bill(bill_id: int, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    return _bill_out(bills_service.get_bill(db, bill_id, user.id))


@router.put(
    "/{bill_id}", response_model=BillResponse,
    summary="Update a bill (partial)",
    responses={404: {"description": "Not found"}},
)
def update_bill(bill_id: int, payload: BillUpdate, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    bill = bills_service.update_bill(
        db, bill_id, user.id, payload.model_dump(exclude_unset=True)
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
def pay_bill(bill_id: int, payload: BillPayRequest, db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    _bill, payment = bills_service.pay_bill(
        db, bill_id, user.id, amount=payload.amount, account_id=payload.account_id,
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
def delete_bill(bill_id: int, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    bills_service.delete_bill(db, bill_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


# ==================== Bill Occurrences (scheduler) ====================


def _occ_out(occ) -> BillOccurrenceResponse:
    return BillOccurrenceResponse(
        id=occ.id, bill_id=occ.bill_id,
        bill_name=occ.bill.name if occ.bill else None,
        due_date=occ.due_date, amount=occ.amount,
        status=occ.status.value if hasattr(occ.status, "value") else occ.status,
        bill_payment_id=occ.bill_payment_id,
        created_at=occ.created_at,
    )


@router.post(
    "/occurrences/run",
    status_code=http_status.HTTP_201_CREATED,
    summary="Generate pending bill occurrences (scheduler job)",
    description=(
        "Materialise DUE occurrences for all active bills up to the given "
        "date. Idempotent - re-running creates zero duplicates."
    ),
)
def generate_occurrences(
    as_of: Optional[date] = Query(None, description="Defaults to today"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    from datetime import date as _date
    created = bills_service.generate_bill_occurrences(
        db, as_of=as_of or _date.today(), user_id=user.id)
    return {"created": created, "as_of": (as_of or _date.today()).isoformat()}


@router.get(
    "/occurrences/due",
    summary="List unpaid (DUE) bill occurrences",
    description="All occurrences up to as_of that have not yet been paid.",
)
def list_due_occurrences(
    as_of: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    from datetime import date as _date
    items = bills_service.due_occurrences(
        db, user_id=user.id, as_of=as_of or _date.today())
    return {"items": [_occ_out(i).model_dump() for i in items],
            "total": len(items)}


@router.post(
    "/occurrences/{occurrence_id}/pay",
    response_model=BillPaymentResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Pay a specific generated occurrence",
    description=(
        "Creates the financial transaction via the normal pay_bill path "
        "and marks the occurrence PAID. Idempotent - a second pay returns 400."
    ),
    responses={201: {"description": "Paid"}, 400: {"description": "Not DUE"}},
)
def pay_occurrence(
    occurrence_id: int, payload: BillPayRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    _bill, payment, _occ = bills_service.pay_occurrence(
        db, occurrence_id, user.id,
        amount=payload.amount, account_id=payload.account_id,
        pay_date=payload.pay_date or date.today(),
    )
    return BillPaymentResponse(
        id=payment.id, bill_id=payment.bill_id, amount=payment.amount,
        paid_date=payment.paid_date, transaction_id=payment.transaction_id,
    )
