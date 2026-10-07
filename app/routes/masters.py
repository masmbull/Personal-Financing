"""Master-data UI: Merchant + PaymentMethod management.

Mirrors the categories HTML pattern. Only the user's OWN custom rows are
mutable; global seed rows (user_id NULL) are shown read-only.
"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Category, MerchantType, PaymentMethodType
from app.api.audit_decorator import audit_action
from app.services import merchants as merchants_service
from app.services import payment_methods as pm_service
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/merchants", response_class=HTMLResponse)
def list_merchants(request: Request, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    merchants = merchants_service.list_merchants(db, user.id)
    return templates.TemplateResponse(request, "merchants/list.html", {
        "merchants": merchants, "MerchantType": MerchantType,
    })


@router.get("/merchants/create", response_class=HTMLResponse)
def create_merchant_form(request: Request, db: Session = Depends(get_db),
                         user: CurrentUser = Depends(get_current_user)):
    categories = db.query(Category).order_by(Category.name).all()
    return templates.TemplateResponse(request, "merchants/create.html", {
        "categories": categories, "MerchantType": MerchantType,
    })


@router.post("/merchants/create")
@audit_action(action="merchant_create", entity="merchant")
def create_merchant(request: Request, canonical_name: str = Form(...),
                    merchant_type: str = Form("OTHER"), category_id: str = Form(""),
                    aliases: str = Form(""), db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    try:
        merchants_service.create_merchant(
            db, user_id=user.id, canonical_name=canonical_name,
            merchant_type=MerchantType(merchant_type),
            category_id=int(category_id) if category_id else None,
            aliases=[a.strip() for a in aliases.split(",") if a.strip()],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/merchants", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/merchants/delete/{merchant_id}")
@audit_action(action="merchant_delete", entity="merchant")
def delete_merchant(merchant_id: int, request: Request, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    try:
        merchants_service.delete_merchant(db, merchant_id, user.id)
    except merchants_service.MerchantNotFound:
        raise HTTPException(status_code=404, detail="Merchant not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/merchants", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/payment-methods", response_class=HTMLResponse)
def list_payment_methods(request: Request, db: Session = Depends(get_db),
                         user: CurrentUser = Depends(get_current_user)):
    methods = pm_service.list_payment_methods(db, user.id)
    return templates.TemplateResponse(request, "payment_methods/list.html", {
        "methods": methods, "PaymentMethodType": PaymentMethodType,
    })


@router.get("/payment-methods/create", response_class=HTMLResponse)
def create_payment_method_form(request: Request,
                               user: CurrentUser = Depends(get_current_user)):
    return templates.TemplateResponse(request, "payment_methods/create.html", {
        "PaymentMethodType": PaymentMethodType,
    })


@router.post("/payment-methods/create")
@audit_action(action="payment_method_create", entity="payment_method")
def create_payment_method(request: Request, name: str = Form(...),
                          method_type: str = Form(...),
                          db: Session = Depends(get_db),
                          user: CurrentUser = Depends(get_current_user)):
    try:
        pm_service.create_payment_method(
            db, user_id=user.id, name=name,
            method_type=PaymentMethodType(method_type),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/payment-methods", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/payment-methods/delete/{pm_id}")
@audit_action(action="payment_method_delete", entity="payment_method")
def delete_payment_method(pm_id: int, request: Request, db: Session = Depends(get_db),
                          user: CurrentUser = Depends(get_current_user)):
    try:
        pm_service.delete_payment_method(db, pm_id, user.id)
    except pm_service.PaymentMethodNotFound:
        raise HTTPException(status_code=404, detail="Payment method not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/payment-methods", status_code=status.HTTP_303_SEE_OTHER)