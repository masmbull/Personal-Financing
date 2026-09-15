"""CSV Import web route — upload page + preview + confirm."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request, user: CurrentUser = Depends(get_current_user),
                db: Session = Depends(get_db)):
    from app.models.models import Account
    accounts = db.query(Account).filter(
        Account.user_id == user.id
    ).order_by(Account.name).all()
    return templates.TemplateResponse(request, "import/index.html", {
        "accounts": accounts,
    })
