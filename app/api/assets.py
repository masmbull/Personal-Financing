from fastapi import APIRouter, Depends, Response, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas.asset import (
    AssetCreate, AssetListResponse, AssetResponse, AssetUpdate,
)
from app.services import assets as assets_service

router = APIRouter(prefix="/assets", tags=["assets"])


def _out(asset) -> AssetResponse:
    return AssetResponse(**assets_service.to_response_dict(asset))


@router.get(
    "", response_model=AssetListResponse,
    summary="List physical assets",
    description="Each item includes gain_loss = current_value - purchase_value.",
)
def list_assets(db: Session = Depends(get_db)):
    assets = assets_service.list_assets(db)
    items = [_out(a) for a in assets]
    return AssetListResponse(
        items=items, total=len(items),
        total_value=sum(a.current_value for a in assets),
    )


@router.post(
    "", response_model=AssetResponse, status_code=http_status.HTTP_201_CREATED,
    summary="Register an asset",
)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)):
    asset = assets_service.create_asset(
        db, name=payload.name, asset_type=payload.asset_type,
        current_value=payload.current_value,
        purchase_value=payload.purchase_value,
        purchase_date=payload.purchase_date,
        icon=payload.icon or "", notes=payload.notes or "",
    )
    return _out(asset)


@router.get(
    "/{asset_id}", response_model=AssetResponse,
    summary="Get one asset", responses={404: {"description": "Not found"}},
)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    return _out(assets_service.get_asset(db, asset_id))


@router.put(
    "/{asset_id}", response_model=AssetResponse,
    summary="Update an asset (partial)",
    responses={404: {"description": "Not found"}},
)
def update_asset(asset_id: int, payload: AssetUpdate,
                 db: Session = Depends(get_db)):
    asset = assets_service.update_asset(
        db, asset_id, payload.model_dump(exclude_unset=True)
    )
    return _out(asset)


@router.delete(
    "/{asset_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete an asset",
    responses={404: {"description": "Not found"}},
)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    assets_service.delete_asset(db, asset_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)