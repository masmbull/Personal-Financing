from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import Category, TransactionType
from app.services.finance import has_transactions_for_category
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/categories", response_class=HTMLResponse)
def list_categories(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.type, Category.name).all()
    return templates.TemplateResponse("categories/list.html", {
        "request": request, "categories": categories,
        "TransactionType": TransactionType,
    })


@router.get("/categories/create", response_class=HTMLResponse)
def create_category_form(request: Request):
    return templates.TemplateResponse("categories/create.html", {
        "request": request, "TransactionType": TransactionType,
    })


@router.post("/categories/create")
def create_category(name: str = Form(...), type: str = Form(...), icon: str = Form(""),
                    db: Session = Depends(get_db)):
    if not name.strip():
        raise HTTPException(status_code=400, detail="Category name required")
    cat = Category(name=name.strip(), type=TransactionType(type), icon=icon or None)
    db.add(cat)
    db.commit()
    return RedirectResponse(url="/categories", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/categories/edit/{cat_id}", response_class=HTMLResponse)
def edit_category_form(cat_id: int, request: Request, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return templates.TemplateResponse("categories/edit.html", {
        "request": request, "category": cat, "TransactionType": TransactionType,
    })


@router.post("/categories/edit/{cat_id}")
def edit_category(cat_id: int, name: str = Form(...), type: str = Form(...),
                  icon: str = Form(""), db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.name = name.strip()
    cat.type = TransactionType(type)
    cat.icon = icon or None
    db.commit()
    return RedirectResponse(url="/categories", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/categories/delete/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if has_transactions_for_category(db, cat_id):
        raise HTTPException(status_code=400, detail="Cannot delete category with existing transactions")
    db.delete(cat)
    db.commit()
    return RedirectResponse(url="/categories", status_code=status.HTTP_303_SEE_OTHER)
