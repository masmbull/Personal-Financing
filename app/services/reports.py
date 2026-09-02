"""Report service - period aggregates shared by API and future frontends.

All date filters are inclusive. Defaults cover the current calendar month.
"""
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Category, Transaction, TransactionType
from app.services.accounts import compute_net_worth
from app.services.finance import expense_between, income_between


def _default_range(date_from: date | None, date_to: date | None):
    today = date.today()
    return (date_from or today.replace(day=1), date_to or today)


def cash_flow(db: Session, user_id: int, date_from: date | None = None,
              date_to: date | None = None) -> dict:
    start, end = _default_range(date_from, date_to)
    income = income_between(db, start, end, user_id)
    expense = expense_between(db, start, end, user_id)
    return {"date_from": start, "date_to": end,
            "income": income, "expense": expense, "net": income - expense}


def category_breakdown(db: Session, tx_type: TransactionType,
                       date_from: date | None = None,
                       date_to: date | None = None,
                       user_id: int | None = None) -> dict:
    start, end = _default_range(date_from, date_to)
    rows = (
        db.query(
            Category.id, Category.name, Category.icon,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .filter(Transaction.type == tx_type,
                Transaction.date >= start, Transaction.date <= end)
    )
    if user_id is not None:
        rows = rows.filter(Transaction.user_id == user_id)
    rows = rows.group_by(Category.id) \
        .order_by(func.sum(Transaction.amount).desc()).all()
    grand = sum(r.total for r in rows)
    by_category = [
        {
            "category_id": r.id, "name": r.name, "icon": r.icon,
            "total": r.total,
            "percentage": round(r.total * 100 / grand, 1) if grand else 0.0,
        }
        for r in rows
    ]
    return {"date_from": start, "date_to": end,
            "type": tx_type.value, "total": grand, "by_category": by_category}


def monthly_series(db: Session, months: int = 6,
                   date_from: date | None = None,
                   date_to: date | None = None,
                   user_id: int = 0) -> list[dict]:
    """Income/expense per month. Uses the explicit range when provided,
    otherwise the trailing `months` months including the current one."""
    series = []
    if date_from and date_to:
        cursor_year, cursor_month = date_from.year, date_from.month
        end_year, end_month = date_to.year, date_to.month
        while (cursor_year, cursor_month) <= (end_year, end_month):
            series.append((cursor_year, cursor_month))
            cursor_month += 1
            if cursor_month > 12:
                cursor_month, cursor_year = 1, cursor_year + 1
    else:
        today = date.today()
        for i in range(months - 1, -1, -1):
            m, y = today.month - i, today.year
            while m <= 0:
                m += 12
                y -= 1
            series.append((y, m))

    out = []
    today = date.today()
    for year, month in series:
        first = date(year, month, 1)
        last = min(_month_end(year, month), today)
        inc = income_between(db, first, last, user_id)
        exp = expense_between(db, first, last, user_id)
        out.append({
            "year": year, "month": month,
            "label": first.strftime("%b %Y"),
            "income": inc, "expense": exp, "net": inc - exp,
        })
    return out


def net_worth_snapshot(db: Session, user_id: int) -> dict:
    nw = compute_net_worth(db, user_id)
    return {
        "as_of": date.today(),
        "net_worth": nw["net_worth"],
        "total_assets": nw["total_assets"],
        "total_liabilities": nw["total_liabilities"],
    }


# ---------- Net-worth history (daily snapshots) ----------


def record_daily_snapshot(db: Session, user_id: int,
                          snapshot_date: date | None = None) -> "NetWorthSnapshot":
    """Upsert one snapshot row per (user, date). Idempotent - calling twice
    for the same logical date refreshes the same row instead of duplicating.
    Supports historical dates, so a job can backfill previous days.
    """
    from app.models.models import NetWorthSnapshot
    from app.time_utils import today_in_tz

    snap_date = snapshot_date or today_in_tz()
    nw = compute_net_worth(db, user_id)
    row = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.snapshot_date == snap_date,
                NetWorthSnapshot.user_id == user_id)
        .first()
    )
    if row is None:
        row = NetWorthSnapshot(
            user_id=user_id,
            snapshot_date=snap_date,
            total_assets=nw["total_assets"],
            total_liabilities=nw["total_liabilities"],
            net_worth=nw["net_worth"],
        )
        db.add(row)
    else:
        row.total_assets = nw["total_assets"]
        row.total_liabilities = nw["total_liabilities"]
        row.net_worth = nw["net_worth"]
    db.commit()
    db.refresh(row)
    return row


def run_daily_net_worth_snapshots(db: Session, as_of: date | None = None) -> int:
    """Create/refresh the daily net-worth snapshot for EVERY active user for a
    logical date (default: today in the canonical timezone). Idempotent per
    (user, date). Returns the number of snapshots written (upserted rows).

    Callable independently of any scheduler - the production caller decides
    when to invoke it.
    """
    from app.models.models import User, NetWorthSnapshot
    from app.time_utils import today_in_tz

    snap_date = as_of or today_in_tz()
    users = db.query(User.id).filter(User.is_active == 1).all()
    written = 0
    for (uid,) in users:
        before = row_count(db, NetWorthSnapshot, uid, snap_date)
        record_daily_snapshot(db, uid, snap_date)
        after = row_count(db, NetWorthSnapshot, uid, snap_date)
        written += after - before
    return written


def row_count(db, model, user_id, snap_date):
    return db.query(model.id).filter(
        model.user_id == user_id,
        model.snapshot_date == snap_date,
    ).count()


def net_worth_history(db: Session, user_id: int, date_from=None,
                      date_to=None) -> list[dict]:
    from app.models.models import NetWorthSnapshot

    query = db.query(NetWorthSnapshot).filter(
        NetWorthSnapshot.user_id == user_id
    ).order_by(NetWorthSnapshot.snapshot_date)
    if date_from:
        query = query.filter(NetWorthSnapshot.snapshot_date >= date_from)
    if date_to:
        query = query.filter(NetWorthSnapshot.snapshot_date <= date_to)
    return [
        {
            "date": r.snapshot_date,
            "net_worth": r.net_worth,
            "total_assets": r.total_assets,
            "total_liabilities": r.total_liabilities,
        }
        for r in query.all()
    ]


def _month_end(year: int, month: int) -> date:
    import calendar
    return date(year, month, calendar.monthrange(year, month)[1])
