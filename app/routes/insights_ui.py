"""Insights web route — spending insights page."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.services.insights import generate_insights
from app.services.health_score import compute_health_score
from app.utils import format_rupiah

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request, user: CurrentUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    data = generate_insights(db, user.id)
    health = compute_health_score(db, user.id)
    return templates.TemplateResponse(request, "insights/index.html", {
        "data": data, "health": health, "format_rupiah": format_rupiah,
    })
