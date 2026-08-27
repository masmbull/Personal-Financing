"""Asset record service."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.models import AssetRecord


class AssetNotFound(Exception):
    pass


ASSET_TYPES = [
    "Kendaraan", "Properti", "Elektronik", "Perhiasan", "Furniture",
    "Peralatan", "Lainnya",
]


def get_asset(db: Session, asset_id: int) -> AssetRecord:
    asset = db.query(AssetRecord).filter(AssetRecord.id == asset_id).first()
    if not asset:
        raise AssetNotFound(f"Asset {asset_id} not found")
    return asset


def list_assets(db: Session):
    return db.query(AssetRecord).order_by(AssetRecord.name).all()


def to_response_dict(asset: AssetRecord) -> dict:
    d = {
        "id": asset.id, "name": asset.name, "asset_type": asset.asset_type,
        "current_value": asset.current_value,
        "purchase_value": asset.purchase_value,
        "purchase_date": asset.purchase_date,
        "icon": asset.icon, "notes": asset.notes,
        "created_at": asset.created_at, "updated_at": asset.updated_at,
        "gain_loss": None,
    }
    if asset.purchase_value is not None:
        d["gain_loss"] = asset.current_value - asset.purchase_value
    return d


def create_asset(db: Session, **fields) -> AssetRecord:
    asset = AssetRecord(
        name=(fields["name"] or "").strip(),
        asset_type=fields["asset_type"],
        current_value=int(fields["current_value"]),
        purchase_value=fields.get("purchase_value"),
        purchase_date=fields.get("purchase_date"),
        icon=(fields.get("icon") or "").strip() or None,
        notes=(fields.get("notes") or "").strip() or None,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, asset_id: int, fields: dict) -> AssetRecord:
    asset = get_asset(db, asset_id)
    for key in ("name", "asset_type", "current_value", "purchase_value",
                "purchase_date", "icon", "notes"):
        value = fields.get(key)
        if value is not None:
            setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset_id: int) -> None:
    asset = get_asset(db, asset_id)
    db.delete(asset)
    db.commit()
