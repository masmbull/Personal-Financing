"""Recurring transactions API."""
from datetime import date

from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.database.db import get_db
from app.services.recurring import (
    RecurringNotFound, create_recurring, delete_recurring,
    generate_recurring_transactions, get_recurring,
    list_recurring, row_payload, update_recurring,
)

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("", summary="List recurring transactions")
def list_recurring_api(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [row_payload(r) for r in list_recurring(db, user.id)]


@router.post("", status_code=http_status.HTTP_201_CREATED,
             summary="Create recurring transaction")
def create_recurring_api(
    payload: dict,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r = create_recurring(
        db,
        user_id=user.id,
        account_id=int(payload["account_id"]),
        category_id=payload.get("category_id"),
        tx_type=payload.get("type", "EXPENSE"),
        amount=int(payload["amount"]),
        description=payload.get("description"),
        frequency=payload.get("frequency", "MONTHLY"),
        start_date=date.fromisoformat(payload["start_date"]),
        notes=payload.get("notes"),
    )
    return row_payload(r)


@router.get("/{rec_id}", summary="Get one recurring transaction")
def get_recurring_api(
    rec_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return row_payload(get_recurring(db, rec_id, user.id))
    except RecurringNotFound:
        return Response(status_code=http_status.HTTP_404_NOT_FOUND)


@router.put("/{rec_id}", summary="Update recurring transaction")
def update_recurring_api(
    rec_id: int,
    payload: dict,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        fields = {k: v for k, v in payload.items()
                  if k in {"amount", "description", "frequency",
                           "next_due_date", "active", "notes",
                           "category_id", "account_id"}}
        if "next_due_date" in fields and isinstance(fields["next_due_date"], str):
            fields["next_due_date"] = date.fromisoformat(fields["next_due_date"])
        r = update_recurring(db, rec_id, user.id, **fields)
        return row_payload(r)
    except RecurringNotFound:
        return Response(status_code=http_status.HTTP_404_NOT_FOUND)


@router.delete("/{rec_id}", status_code=http_status.HTTP_204_NO_CONTENT,
               summary="Delete recurring transaction")
def delete_recurring_api(
    rec_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_recurring(db, rec_id, user.id)
    except RecurringNotFound:
        pass
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post("/run", summary="Manually trigger recurring generation")
def run_recurring(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    created = generate_recurring_transactions(db, user_id=user.id)
    return {"created": created}
