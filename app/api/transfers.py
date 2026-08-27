from datetime import date

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.models import TransactionType
from app.schemas.transfer import TransferCreate, TransferResponse
from app.services.finance import create_transaction

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post(
    "", response_model=TransferResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Transfer money between own accounts",
    description=(
        "Moves money from one own account to another. Transfers are stored "
        "with type TRANSFER and are NEVER counted as income or expense in "
        "balances, dashboard or reports."
    ),
    responses={
        201: {"description": "Transfer recorded"},
        400: {"description": "Invalid transfer (same account, unknown account, bad amount)"},
    },
)
def create_transfer(payload: TransferCreate, db: Session = Depends(get_db)):
    tx = create_transaction(
        db=db, type=TransactionType.TRANSFER, amount=payload.amount,
        account_id=payload.from_account_id, category_id=None,
        date_val=payload.date or date.today(),
        description=payload.description,
        transfer_to_account_id=payload.to_account_id,
    )
    return TransferResponse(
        transaction_id=tx.id,
        from_account_id=payload.from_account_id,
        to_account_id=payload.to_account_id,
        amount=payload.amount,
        date=tx.date,
        description=tx.description,
    )