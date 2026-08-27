from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

MORE_LINKS = [
    ("/debts", "💸", "Hutang & Piutang", "Catat uang pinjam dan piutang"),
    ("/bills", "📄", "Tagihan", "Tagihan rutin bulanan"),
    ("/budgets", "📊", "Budget", "Batas belanja per kategori"),
    ("/savings", "🎯", "Tabungan", "Target nabung"),
    ("/assets", "🏠", "Aset", "Barang & properti berharga"),
    ("/investments", "📈", "Investasi", "Saham, emas, crypto"),
    ("/accounts", "🏦", "Akun", "Rekening, e-wallet, kas"),
    ("/categories", "🏷️", "Kategori", "Atur kategori transaksi"),
]


@router.get("/more", response_class=HTMLResponse)
def more_page(request: Request):
    return templates.TemplateResponse("more.html", {
        "request": request, "links": MORE_LINKS,
    })
