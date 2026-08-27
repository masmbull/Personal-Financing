from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services.finance import get_report_data
from app.utils import format_rupiah
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/reports", response_class=HTMLResponse)
def reports(request: Request, db: Session = Depends(get_db)):
    data = get_report_data(db)
    return templates.TemplateResponse(request, "reports/index.html", { "data": data, "format_rupiah": format_rupiah,
    })
