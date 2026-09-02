"""PaymentMethod API — ownership-scoped."""
from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.models.models import PaymentMethodType
from app.schemas.payment_method import (
    PaymentMethodCreate, PaymentMethodListResponse, PaymentMethodResponse,
    PaymentMethodUpdate,
)
from app.services import payment_methods as svc

router = APIRouter(prefix="/payment-methods", tags=["payment-methods"])


def _out(pm):
    return svc._to_response(pm)


@router.get("", response_model=PaymentMethodListResponse)
def list_payment_methods(method_type: PaymentMethodType | None = None,
                         db: Session = Depends(get_db),
                         user: CurrentUser = Depends(get_current_user)):
    items = [_out(pm) for pm in svc.list_payment_methods(db, user.id, method_type)]
    return PaymentMethodListResponse(items=items, total=len(items))


@router.post("", response_model=PaymentMethodResponse, status_code=http_status.HTTP_201_CREATED)
def create_payment_method(payload: PaymentMethodCreate,
                          db: Session = Depends(get_db),
                          user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        pm = svc.create_payment_method(
            db, user_id=user.id, name=payload.name, method_type=payload.method_type,
            source=payload.source, source_url=payload.source_url, notes=payload.notes,
        )
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return _out(pm)


@router.get("/{pm_id}", response_model=PaymentMethodResponse)
def get_payment_method(pm_id: int, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        pm = svc.get_payment_method_or_raise(db, pm_id, user.id)
    except svc.PaymentMethodNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    return _out(pm)


@router.put("/{pm_id}", response_model=PaymentMethodResponse)
def update_payment_method(pm_id: int, payload: PaymentMethodUpdate,
                          db: Session = Depends(get_db),
                          user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        pm = svc.update_payment_method(db, pm_id, user.id,
                                       **payload.model_dump(exclude_unset=True))
    except svc.PaymentMethodNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    return _out(pm)


@router.delete("/{pm_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_payment_method(pm_id: int, db: Session = Depends(get_db),
                          user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        svc.delete_payment_method(db, pm_id, user.id)
    except svc.PaymentMethodNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
