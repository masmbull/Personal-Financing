"""Financial institution API — global master read + own CRUD + ownership."""
from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.institution import (
    InstitutionCreate, InstitutionListResponse, InstitutionResponse,
    InstitutionUpdate,
)
from app.services import institutions as inst_service

router = APIRouter(prefix="/institutions", tags=["institutions"])


def _out(inst) -> InstitutionResponse:
    return InstitutionResponse(
        id=inst.id, code=inst.code, legal_name=inst.legal_name,
        short_name=inst.short_name, aliases=inst.aliases,
        institution_type=inst.institution_type, swift_bic=inst.swift_bic,
        active=bool(inst.active), source=inst.source, source_url=inst.source_url,
        notes=inst.notes, effective_from=inst.effective_from,
        effective_until=inst.effective_until, verified_at=inst.verified_at,
    )


@router.get("", response_model=InstitutionListResponse,
            summary="List financial institutions (global + own)")
def list_institutions(db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    items = [_out(i) for i in inst_service.list_institutions(db, user.id)]
    return InstitutionListResponse(items=items, total=len(items))


@router.post("", response_model=InstitutionResponse,
             status_code=http_status.HTTP_201_CREATED,
             summary="Create own financial institution")
def create_institution(payload: InstitutionCreate,
                       db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    inst = inst_service.create_institution(
        db, user_id=user.id, code=payload.code, legal_name=payload.legal_name,
        short_name=payload.short_name, institution_type=payload.institution_type,
        aliases=payload.aliases, swift_bic=payload.swift_bic, active=payload.active,
        source=payload.source, source_url=payload.source_url, notes=payload.notes,
        effective_from=payload.effective_from, effective_until=payload.effective_until,
    )
    return _out(inst)


@router.get("/{institution_id}", response_model=InstitutionResponse,
            summary="Get an institution (global or own)")
def get_institution(institution_id: int, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    inst = inst_service.get_institution_or_raise(db, institution_id, user.id)
    return _out(inst)


@router.put("/{institution_id}", response_model=InstitutionResponse,
            summary="Update OWN institution only")
def update_institution(institution_id: int, payload: InstitutionUpdate,
                       db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    fields = payload.model_dump(exclude_unset=True)
    inst = inst_service.update_institution(db, institution_id, user.id, **fields)
    return _out(inst)


@router.delete("/{institution_id}", status_code=http_status.HTTP_204_NO_CONTENT,
               summary="Delete OWN institution only (global rows forbidden)")
def delete_institution(institution_id: int, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(get_current_user)):
    inst_service.delete_institution(db, institution_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
