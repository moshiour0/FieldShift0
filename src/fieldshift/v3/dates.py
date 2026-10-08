"""Shared inclusive evidence-date validation for the API and the engine."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def evidence_dates(start_date=None, end_date=None, *, year: int = 2026) -> tuple[date, date]:
    if (start_date is None) != (end_date is None):
        raise ValueError("Provide both start_date and end_date (YYYY-MM-DD).")
    today = datetime.now(UTC).date()
    if start_date is None:
        end = min(date(year, 12, 31), today - timedelta(days=14))
        start = date(min(year, end.year), 1, 1)
        return start, end
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except (TypeError, ValueError) as exc:
        raise ValueError("Dates must be valid calendar dates in YYYY-MM-DD format.") from exc
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    if start < date(2000, 1, 1) or end > today:
        raise ValueError("Choose dates from 2000-01-01 through today; observations cannot be requested in the future.")
    if (end - start).days >= 366:
        raise ValueError("Choose an evidence window of at most 366 days (both endpoints included).")
    return start, end
