"""Canonical application timezone helpers.

The whole financial domain works on calendar dates (naive ``datetime.date``).
This module is the single source of truth for "today" so that daily jobs
(bill auto-post, net-worth snapshots) resolve the same date consistently
regardless of the machine clock. The timezone is configurable via
``APP_TIMEZONE`` and defaults to Asia/Jakarta (Indonesia-first).
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def app_timezone() -> ZoneInfo:
    """Return the configured application IANA timezone."""
    return ZoneInfo(get_settings().APP_TIMEZONE)


def today_in_tz() -> date:
    """Return the current calendar date in the application timezone."""
    return datetime.now(app_timezone()).date()


def tz_label() -> str:
    """Human label of the canonical timezone (e.g. 'Asia/Jakarta')."""
    return get_settings().APP_TIMEZONE
