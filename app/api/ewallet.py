"""E-wallet / e-money provider API — global master read + own CRUD + ownership."""
from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.ewallet import (
    ProviderCreate, ProviderListResponse, ProviderResponse, ProviderUpdate,
)
from app.services import ewallet as ew_service

router = APIRouter(prefix="/ewallet-providers", tags=["ewallet-providers"])


def _out(p) -> ProviderResponse:
    return ProviderResponse(
        id=p.id, code=p.code, legal_name=p.legal_name, short_name=p.short_name,
        aliases=p.aliases, operator_type=p.operator_type, active=bool(p.active),
        source=p.source, source_url=p.source_url, notes=p.notes,
        effective_from=p.effective_from, effective_until=p.effective_until,
        verified_at=p.verified_at,
    )


@router.get("", response_model=ProviderListResponse,
            summary="List e-wallet providers (global + own)")
def list_providers(db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    items = [_out(p) for p in ew_service.list_providers(db, user.id)]
    return ProviderListResponse(items=items, total=len(items))


@router.post("", response_model=ProviderResponse,
             status_code=http_status.HTTP_201_CREATED,
             summary="Create own e-wallet provider")
def create_provider(payload: ProviderCreate, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    p = ew_service.create_provider(
        db, user_id=user.id, code=payload.code, legal_name=payload.legal_name,
        short_name=payload.short_name, aliases=payload.aliases,
        operator_type=payload.operator_type, active=payload.active,
        source=payload.source, source_url=payload.source_url, notes=payload.notes,
        effective_from=payload.effective_from, effective_until=payload.effective_until,
    )
    return _out(p)


@router.get("/{provider_id}", response_model=ProviderResponse,
            summary="Get a provider (global or own)")
def get_provider(provider_id: int, db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    p = ew_service.get_provider_or_raise(db, provider_id, user.id)
    return _out(p)


@router.put("/{provider_id}", response_model=ProviderResponse,
            summary="Update OWN provider only")
def update_provider(provider_id: int, payload: ProviderUpdate,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    fields = payload.model_dump(exclude_unset=True)
    p = ew_service.update_provider(db, provider_id, user.id, **fields)
    return _out(p)


@router.delete("/{provider_id}", status_code=http_status.HTTP_204_NO_CONTENT,
               summary="Delete OWN provider only (global rows forbidden)")
def delete_provider(provider_id: int, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    ew_service.delete_provider(db, provider_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
