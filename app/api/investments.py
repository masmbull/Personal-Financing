from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas.investment import (
    InvestmentCreate, InvestmentListResponse, InvestmentResponse, InvestmentUpdate,
)
from app.services import investments as investments_service

router = APIRouter(prefix="/investments", tags=["investments"])


def _out(inv) -> InvestmentResponse:
    return InvestmentResponse(**investments_service.to_response_dict(inv))


@router.get(
    "", response_model=InvestmentListResponse,
    summary="List investments with totals",
    description="Items include gain_loss and return_percentage; response carries grand totals.",
)
def list_investments(db: Session = Depends(get_db)):
    data = investments_service.totals(db)
    return InvestmentListResponse(
        items=[InvestmentResponse(**i) for i in data["items"]],
        total=len(data["items"]),
        total_invested=data["total_invested"],
        total_current_value=data["total_current_value"],
        total_gain_loss=data["total_gain_loss"],
    )


@router.post(
    "", response_model=InvestmentResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Record an investment holding",
)
def create_investment(payload: InvestmentCreate, db: Session = Depends(get_db)):
    inv = investments_service.create_investment(
        db, name=payload.name, investment_type=payload.investment_type,
        amount_invested=payload.amount_invested,
        current_value=payload.current_value,
        purchase_date=payload.purchase_date,
        icon=payload.icon or "", notes=payload.notes or "",
    )
    return _out(inv)


@router.get(
    "/{investment_id}", response_model=InvestmentResponse,
    summary="Get one investment",
    responses={404: {"description": "Not found"}},
)
def get_investment(investment_id: int, db: Session = Depends(get_db)):
    return _out(investments_service.get_investment(db, investment_id))


@router.put(
    "/{investment_id}", response_model=InvestmentResponse,
    summary="Update investment (partial)",
    description="Typically used to refresh current_value with the latest market price.",
    responses={404: {"description": "Not found"}},
)
def update_investment(investment_id: int, payload: InvestmentUpdate,
                      db: Session = Depends(get_db)):
    inv = investments_service.update_investment(
        db, investment_id, payload.model_dump(exclude_unset=True)
    )
    return _out(inv)


@router.delete(
    "/{investment_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete an investment record",
    responses={404: {"description": "Not found"}},
)
def delete_investment(investment_id: int, db: Session = Depends(get_db)):
    investments_service.delete_investment(db, investment_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)