from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Account
from app.services.finance import create_transaction
from app.models.models import TransactionType
from app.utils import today_str
from datetime import date
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/transfer", response_class=HTMLResponse)
def transfer_form(request: Request, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    accounts = db.query(Account).filter(
        (Account.user_id == user.id) | (Account.user_id.is_(None))
    ).order_by(Account.name).all()
    return templates.TemplateResponse(request, "transfer/index.html", { "accounts": accounts, "today": today_str(),
    })


@router.post("/transfer")
def do_transfer(
    from_account_id: str = Form(...),
    to_account_id: str = Form(...),
    amount: str = Form(...),
    date_val: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        amount_int = int(amount)
        tx_date = date.fromisoformat(date_val)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid input")
    if amount_int <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    try:
        create_transaction(
            db=db, user_id=user.id, type=TransactionType.TRANSFER, amount=amount_int,
            account_id=int(from_account_id), category_id=None,
            date_val=tx_date, description=description.strip() if description else None,
            transfer_to_account_id=int(to_account_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
