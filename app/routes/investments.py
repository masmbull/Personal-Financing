from datetime import date

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import investments as investments_service
from app.utils import format_rupiah, today_str
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/investments", response_class=HTMLResponse)
def list_investments(request: Request, db: Session = Depends(get_db)):
    items = [investments_service.to_response_dict(i)
             for i in investments_service.list_investments(db)]
    total_invested = sum(i["amount_invested"] for i in items)
    total_current = sum(i["current_value"] for i in items)
    total_return = total_current - total_invested
    pct = round(total_return * 100 / total_invested, 1) if total_invested > 0 else 0
    # Template iterates ORM-like objects; keep attribute access working
    class _Row:
        def __init__(self, d):
            self.__dict__.update(d)
    rows = [_Row(i) for i in items]
    return templates.TemplateResponse(request, "investments/list.html", { "investments": rows,
        "total_invested": total_invested, "total_current": total_current,
        "total_return": total_return, "return_pct": pct,
        "format_rupiah": format_rupiah,
        "INVESTMENT_TYPES": investments_service.INVESTMENT_TYPES,
    })


@router.get("/investments/create", response_class=HTMLResponse)
def create_investment_form(request: Request):
    return templates.TemplateResponse(request, "investments/create.html", { "today": today_str(),
        "INVESTMENT_TYPES": investments_service.INVESTMENT_TYPES,
    })


@router.post("/investments/create")
def create_investment(
    name: str = Form(...), investment_type: str = Form(...),
    amount_invested: str = Form(...), current_value: str = Form(...),
    purchase_date: str = Form(""), notes: str = Form(""),
    icon: str = Form(""), db: Session = Depends(get_db),
):
    try:
        investments_service.create_investment(
            db, name=name, investment_type=investment_type,
            amount_invested=int(amount_invested),
            current_value=int(current_value),
            purchase_date=date.fromisoformat(purchase_date) if purchase_date else None,
            notes=notes, icon=icon,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/investments", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/investments/edit/{inv_id}", response_class=HTMLResponse)
def edit_investment_form(inv_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        inv = investments_service.get_investment(db, inv_id)
    except investments_service.InvestmentNotFound:
        raise HTTPException(status_code=404, detail="Investment not found")
    return templates.TemplateResponse(request, "investments/edit.html", { "inv": inv, "today": today_str(),
        "INVESTMENT_TYPES": investments_service.INVESTMENT_TYPES,
    })


@router.post("/investments/edit/{inv_id}")
def edit_investment(
    inv_id: int, name: str = Form(...), investment_type: str = Form(...),
    amount_invested: str = Form(...), current_value: str = Form(...),
    purchase_date: str = Form(""), notes: str = Form(""),
    icon: str = Form(""), db: Session = Depends(get_db),
):
    try:
        investments_service.update_investment(db, inv_id, {
            "name": name.strip(), "investment_type": investment_type,
            "amount_invested": int(amount_invested),
            "current_value": int(current_value),
            "purchase_date": date.fromisoformat(purchase_date) if purchase_date else None,
            "notes": (notes or "").strip() or None,
            "icon": (icon or "").strip() or None,
        })
    except investments_service.InvestmentNotFound:
        raise HTTPException(status_code=404, detail="Investment not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/investments", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/investments/delete/{inv_id}")
def delete_investment(inv_id: int, db: Session = Depends(get_db)):
    try:
        investments_service.delete_investment(db, inv_id)
    except investments_service.InvestmentNotFound:
        raise HTTPException(status_code=404, detail="Investment not found")
    return RedirectResponse(url="/investments", status_code=status.HTTP_303_SEE_OTHER)