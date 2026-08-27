"""Transfer schemas.

Transfers between own accounts move money only - they never count as
income or expense in any report or balance calculation.
"""
from datetime import date as dt_date
from typing import Optional

from pydantic import BaseModel, Field


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: int = Field(gt=0, description="Amount in rupiah")
    date: Optional[dt_date] = None
    description: Optional[str] = Field(
        None, examples=["Transfer BCA ke Cash"]
    )


class TransferResponse(BaseModel):
    transaction_id: int
    from_account_id: int
    to_account_id: int
    amount: int
    date: dt_date
    description: Optional[str] = None
