"""CSV / XLSX export routes — scoped to current user.

Both formats produce their bytes in memory via StreamingResponse so the
response never hits disk and memory usage stays bounded for large datasets.
"""
import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, get_current_user
from app.database.db import get_db
from app.models.models import Category, Transaction, TransactionType
from app.services.finance import expense_between, income_between
from app.utils import format_rupiah

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _bom_csv(rows: list[list[str]], filename: str) -> StreamingResponse:
    """UTF-8 BOM + CSV rows → StreamingResponse (Excel-compatible)."""
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM so Excel opens UTF-8 correctly
    writer = csv.writer(buf)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx(rows: list[list], filename: str, sheet_title: str = "Sheet1") -> StreamingResponse:
    """Rows → single-sheet .xlsx workbook in memory."""
    # ponytail: openpyxl only; drop dep if xlsx export is ever removed.
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]  # Excel sheet-name cap
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _exit_guard_ext(fmt: str) -> str:
    return "xlsx" if fmt == "xlsx" else "csv"


def _transactions_rows(db: Session, user: CurrentUser, *,
                       date_from: str, date_to: str, type_filter: str,
                       category_id: str, tag_id: str) -> list[list]:
    """Shared transaction rows for CSV/XLSX export (header + data)."""
    from app.models.models import TransactionTag
    query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.transfer_to_account),
        )
        .filter(Transaction.user_id == user.id)
    )
    if date_from:
        query = query.filter(Transaction.date >= date.fromisoformat(date_from))
    if date_to:
        query = query.filter(Transaction.date <= date.fromisoformat(date_to))
    if type_filter:
        query = query.filter(Transaction.type == TransactionType(type_filter.upper()))
    if category_id:
        query = query.filter(Transaction.category_id == int(category_id))
    if tag_id:
        tag_tx = db.query(TransactionTag.transaction_id).filter(
            TransactionTag.tag_id == int(tag_id)
        ).subquery()
        query = query.filter(Transaction.id.in_(tag_tx))

    transactions = query.order_by(desc(Transaction.date), desc(Transaction.id)).all()

    rows = [["Tanggal", "Tipe", "Deskripsi", "Kategori", "Akun", "Jumlah"]]
    for tx in transactions:
        type_label = {
            TransactionType.EXPENSE: "Pengeluaran",
            TransactionType.INCOME: "Pemasukan",
            TransactionType.TRANSFER: "Transfer",
        }.get(tx.type, tx.type.value)

        if tx.type == TransactionType.TRANSFER:
            cat_label = "Transfer ke " + (
                tx.transfer_to_account.name if tx.transfer_to_account else "?"
            )
        elif tx.category:
            cat_label = tx.category.name
        else:
            cat_label = ""

        amount_str = format_rupiah(tx.amount)
        if tx.type == TransactionType.EXPENSE:
            amount_str = "-" + amount_str
        elif tx.type == TransactionType.INCOME:
            amount_str = "+" + amount_str

        rows.append([
            tx.date.isoformat(), type_label,
            tx.description or "", cat_label,
            tx.account.name if tx.account else "", amount_str,
        ])

    return rows


def _transactions_export(db: Session, user: CurrentUser, fmt: str, **filters) -> StreamingResponse:
    rows = _transactions_rows(db, user, **filters)
    ext = _exit_guard_ext(fmt)
    filename = f"transaksi_{date.today().isoformat()}.{ext}"
    return _xlsx(rows, filename, "Transaksi") if fmt == "xlsx" else _bom_csv(rows, filename)


@router.get("/transactions/export")
def export_transactions(
    date_from: str = "",
    date_to: str = "",
    type_filter: str = "",
    category_id: str = "",
    tag_id: str = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Export current user's transactions as CSV."""
    return _transactions_export(db, user, "csv", date_from=date_from,
                                date_to=date_to, type_filter=type_filter,
                                category_id=category_id, tag_id=tag_id)


@router.get("/transactions/export.xlsx")
def export_transactions_xlsx(
    date_from: str = "",
    date_to: str = "",
    type_filter: str = "",
    category_id: str = "",
    tag_id: str = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Export current user's transactions as Excel (.xlsx)."""
    return _transactions_export(db, user, "xlsx", date_from=date_from,
                                date_to=date_to, type_filter=type_filter,
                                category_id=category_id, tag_id=tag_id)


def _reports_rows(db: Session, user: CurrentUser, *,
                  date_from: str, date_to: str) -> tuple[list[list], str, str]:
    """Shared report rows (summary + category breakdown) for CSV/XLSX."""
    today = date.today()
    start = date.fromisoformat(date_from) if date_from else today.replace(day=1)
    end = date.fromisoformat(date_to) if date_to else today

    inc = income_between(db, start, end, user.id)
    exp = expense_between(db, start, end, user.id)

    from sqlalchemy import func

    rows = []
    rows.append(["Laporan Keuangan"])
    rows.append([f"Periode: {start.isoformat()} s/d {end.isoformat()}"])
    rows.append([])
    rows.append(["", "Pemasukan", "Pengeluaran", "Selisih"])
    rows.append(["", format_rupiah(inc), format_rupiah(exp), format_rupiah(inc - exp)])
    rows.append([])
    rows.append(["Kategori", "Jumlah", "Persentase"])
    cat_rows = (
        db.query(
            Category.name,
            Category.icon,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.type == TransactionType.EXPENSE,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.user_id == user.id,
        )
        .group_by(Category.id)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )
    for r in cat_rows:
        pct = round(r.total * 100 / exp, 1) if exp else 0
        rows.append([f"{r.icon or ''} {r.name}", format_rupiah(r.total), f"{pct}%"])
    return rows, start.isoformat(), end.isoformat()


def _reports_export(db: Session, user: CurrentUser, fmt: str, **filters) -> StreamingResponse:
    rows, start_iso, end_iso = _reports_rows(db, user, **filters)
    ext = _exit_guard_ext(fmt)
    filename = f"laporan_{start_iso}_{end_iso}.{ext}"
    return _xlsx(rows, filename, "Laporan") if fmt == "xlsx" else _bom_csv(rows, filename)


@router.get("/reports/export")
def export_reports(
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Export expense breakdown by category as CSV."""
    return _reports_export(db, user, "csv", date_from=date_from, date_to=date_to)


@router.get("/reports/export.xlsx")
def export_reports_xlsx(
    date_from: str = "",
    date_to: str = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Export expense breakdown by category as Excel (.xlsx)."""
    return _reports_export(db, user, "xlsx", date_from=date_from, date_to=date_to)
