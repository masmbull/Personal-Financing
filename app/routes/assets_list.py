from datetime import date

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import assets as assets_service
from app.utils import format_rupiah, today_str
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/assets", response_class=HTMLResponse)
def list_assets(request: Request, db: Session = Depends(get_db)):
    assets = assets_service.list_assets(db)
    total_value = sum(a.current_value for a in assets)
    return templates.TemplateResponse(request, "assets/list.html", { "assets": assets, "total_value": total_value,
        "format_rupiah": format_rupiah,
        "ASSET_TYPES": assets_service.ASSET_TYPES,
    })


@router.get("/assets/create", response_class=HTMLResponse)
def create_asset_form(request: Request):
    return templates.TemplateResponse(request, "assets/create.html", { "today": today_str(),
        "ASSET_TYPES": assets_service.ASSET_TYPES,
    })


def _parse_asset_fields(form: dict) -> dict:
    return {
        "name": form.get("name", ""),
        "asset_type": form.get("asset_type", ""),
        "current_value": int(form["current_value"]) if form.get("current_value") else 0,
        "purchase_value": int(form["purchase_value"]) if form.get("purchase_value") else None,
        "purchase_date": date.fromisoformat(form["purchase_date"]) if form.get("purchase_date") else None,
        "notes": form.get("notes", ""),
        "icon": form.get("icon", ""),
    }


@router.post("/assets/create")
def create_asset(
    name: str = Form(...), asset_type: str = Form(...),
    current_value: str = Form(...), purchase_value: str = Form(""),
    purchase_date: str = Form(""), notes: str = Form(""),
    icon: str = Form(""), db: Session = Depends(get_db),
):
    try:
        fields = _parse_asset_fields(locals())
        fields.pop("db", None)
        assets_service.create_asset(db, **fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/assets/edit/{asset_id}", response_class=HTMLResponse)
def edit_asset_form(asset_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        asset = assets_service.get_asset(db, asset_id)
    except assets_service.AssetNotFound:
        raise HTTPException(status_code=404, detail="Asset not found")
    return templates.TemplateResponse(request, "assets/edit.html", { "asset": asset, "today": today_str(),
        "ASSET_TYPES": assets_service.ASSET_TYPES,
    })


@router.post("/assets/edit/{asset_id}")
def edit_asset(
    asset_id: int, name: str = Form(...), asset_type: str = Form(...),
    current_value: str = Form(...), purchase_value: str = Form(""),
    purchase_date: str = Form(""), notes: str = Form(""),
    icon: str = Form(""), db: Session = Depends(get_db),
):
    try:
        fields = _parse_asset_fields(locals())
        fields.pop("db", None)
        assets_service.update_asset(db, asset_id, fields)
    except assets_service.AssetNotFound:
        raise HTTPException(status_code=404, detail="Asset not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/assets/delete/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    try:
        assets_service.delete_asset(db, asset_id)
    except assets_service.AssetNotFound:
        raise HTTPException(status_code=404, detail="Asset not found")
    return RedirectResponse(url="/assets", status_code=status.HTTP_303_SEE_OTHER)