"""Production job entry points - independently callable and idempotent.

The business operations (bill auto-post, daily net-worth snapshot) are pure
service functions that take only a DB session. This module wires them into a
single runnable batch suitable for a cron/systemd timer. Nothing here starts
its own scheduler thread; the deployment layer decides when to call in.

Each job is:
  * idempotent  - safe to rerun; never duplicates financial data
  * observable  - returns a small counts dict for logging
  * user-scoped - only touches the owning user's data
  * timezone-aware - resolves "today" via app.time_utils
"""
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger("app.jobs")


def run_bill_auto_post(db: Session, as_of=None, user_id=None) -> dict:
    """Materialise unpaid DUE bill occurrences (never moves money).

    Returns {"occurrences": N}.
    """
    from app.services.bills import generate_bill_occurrences
    from app.time_utils import today_in_tz
    snap_date = as_of or today_in_tz()
    created = generate_bill_occurrences(db, as_of=snap_date, user_id=user_id)
    logger.info("bill_auto_post as_of=%s occurrences=%d", snap_date, created)
    return {"occurrences": created}


def run_daily_net_worth_snapshots(db: Session, as_of=None) -> dict:
    """Refresh the daily net-worth point for every active user.

    Returns {"snapshots": N}.
    """
    from app.services.reports import run_daily_net_worth_snapshots as _run
    from app.time_utils import today_in_tz
    snap_date = as_of or today_in_tz()
    written = _run(db, snap_date)
    logger.info("net_worth_daily as_of=%s written=%d", snap_date, written)
    return {"snapshots": written}


def run_all_once(db: Session, as_of=None) -> dict:
    """Run every production job once in a single invocation (used by cron)."""
    return {
        "bill_auto_post": run_bill_auto_post(db, as_of=as_of),
        "net_worth_daily": run_daily_net_worth_snapshots(db, as_of=as_of),
    }