"""Lightweight CLI entry-point for production jobs.

Usage (no APScheduler dependency):
    python -m app.jobs_cli bills           # generate bill occurrences
    python -m app.jobs_cli networth        # daily net-worth snapshots
    python -m app.jobs_cli all             # run every job once
    python -m app.jobs_cli all --date 2026-09-01  # historical date

Each command is safe to rerun (idempotent). For a small private deployment,
add the relevant command(s) to a Windows Task Scheduler job or a cron
entry (Linux) that fires once per day. The jobs are pure functions that take
only a DB session; they never start background threads.
"""
import argparse
import logging
import sys
from datetime import date


def main():
    parser = argparse.ArgumentParser(
        description="Run personal-finance production jobs",
    )
    parser.add_argument(
        "job",
        choices=["bills", "networth", "all"],
        help="Which job to run",
    )
    parser.add_argument(
        "--date", dest="as_of", default=None,
        help="Override the logical date (YYYY-MM-DD). Defaults to today in "
             "the canonical timezone (Asia/Jakarta).",
    )
    parser.add_argument(
        "--user-id", type=int, default=None,
        help="Run bill auto-post for ONE user only (useful for testing)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress info-level log output",
    )
    args = parser.parse_args()

    level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    as_of: date | None = None
    if args.as_of:
        as_of = date.fromisoformat(args.as_of)

    from app.database.db import SessionLocal
    db = SessionLocal()
    try:
        if args.job == "bills":
            from app.services.jobs import run_bill_auto_post
            result = run_bill_auto_post(db, as_of=as_of, user_id=args.user_id)
        elif args.job == "networth":
            from app.services.jobs import run_daily_net_worth_snapshots
            result = run_daily_net_worth_snapshots(db, as_of=as_of)
        else:
            from app.services.jobs import run_all_once
            result = run_all_once(db, as_of=as_of)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
