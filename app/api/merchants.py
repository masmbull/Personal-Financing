"""Merchant API — ownership-scoped CRUD + resolve."""
from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.models.models import MerchantType
from app.schemas.merchant import (
    AliasCreate, MerchantCreate, MerchantListResponse, MerchantResolveRequest,
    MerchantResolveResponse, MerchantResponse, MerchantUpdate,
)
from app.services import merchants as svc

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.get("", response_model=MerchantListResponse)
def list_merchants(search: str | None = None, category_id: int | None = None,
                   db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    items = [svc._to_response(m) for m in svc.list_merchants(db, user.id, search, category_id)]
    return MerchantListResponse(items=items, total=len(items))


@router.post("/resolve", response_model=MerchantResolveResponse)
def resolve_merchant(payload: MerchantResolveRequest,
                     db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    return svc.resolve_merchant(db, payload.text, user.id) or {}


@router.post("", response_model=MerchantResponse, status_code=http_status.HTTP_201_CREATED)
def create_merchant(payload: MerchantCreate,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        m = svc.create_merchant(
            db, user_id=user.id, canonical_name=payload.canonical_name,
            display_name=payload.display_name, category_id=payload.category_id,
            merchant_type=payload.merchant_type, source=payload.source,
            source_url=payload.source_url, aliases=payload.aliases,
        )
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return svc._to_response(m)


@router.get("/{merchant_id}", response_model=MerchantResponse)
def get_merchant(merchant_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        m = svc.get_merchant_or_raise(db, merchant_id, user.id)
    except svc.MerchantNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    return svc._to_response(m)


@router.put("/{merchant_id}", response_model=MerchantResponse)
def update_merchant(merchant_id: int, payload: MerchantUpdate,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        m = svc.update_merchant(db, merchant_id, user.id,
                                **payload.model_dump(exclude_unset=True))
    except svc.MerchantNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return svc._to_response(m)


@router.post("/{merchant_id}/aliases", response_model=MerchantResponse)
def add_alias(merchant_id: int, payload: AliasCreate,
              db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        svc.add_alias(db, merchant_id, user.id, payload.alias, payload.source)
        m = svc.get_merchant_or_raise(db, merchant_id, user.id)
    except svc.MerchantNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return svc._to_response(m)


@router.delete("/{merchant_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_merchant(merchant_id: int, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    try:
        svc.delete_merchant(db, merchant_id, user.id)
    except svc.MerchantNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e))
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
