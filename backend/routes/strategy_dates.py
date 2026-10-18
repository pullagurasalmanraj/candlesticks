"""Shared half-open research windows for NSE calendar-day requests."""
import re
from datetime import datetime, timezone

import pandas as pd


RESEARCH_CALENDAR_TIMEZONE = "Asia/Kolkata"
_CALENDAR_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_TIMESTAMP_PREFIX = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt ]")


def _research_date_window(raw_from=None, raw_to=None, *, now=None):
    """Return UTC [start, end) bounds, including the entire date-only end day.

    YYYY-MM-DD inputs describe IST calendar days. Explicit timestamps retain
    their instant; timezone-naive timestamps retain the previous UTC convention.
    An omitted end is the current instant, not tomorrow's calendar boundary.
    """
    def parse(value, field, end=False):
        if value is None or (isinstance(value, str) and not value):
            if end:
                value = now if now is not None else datetime.now(timezone.utc)
                stamp = pd.Timestamp(value)
                return (stamp.tz_localize("UTC") if stamp.tzinfo is None
                        else stamp.tz_convert("UTC"))
            value = "2000-01-01"
        if not isinstance(value, str):
            raise ValueError(f"{field} must be YYYY-MM-DD or an ISO timestamp")
        value = value.strip()
        try:
            if _CALENDAR_DATE.fullmatch(value):
                stamp = pd.Timestamp(value).tz_localize(RESEARCH_CALENDAR_TIMEZONE)
                if end:
                    stamp += pd.DateOffset(days=1)
                return stamp.tz_convert("UTC")
            if not _TIMESTAMP_PREFIX.match(value):
                raise ValueError("Not an ISO date or timestamp")
            stamp = pd.Timestamp(value)
            if pd.isna(stamp) or stamp.nanosecond:
                raise ValueError("Timestamp must have at most microsecond precision")
            return (stamp.tz_localize("UTC") if stamp.tzinfo is None
                    else stamp.tz_convert("UTC"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Invalid {field}; use YYYY-MM-DD or an ISO timestamp with at most 6 fractional digits"
            ) from exc

    start = parse(raw_from, "from_date")
    end = parse(raw_to, "to_date", end=True)
    if start >= end:
        raise ValueError("from_date must be before the exclusive end of to_date")
    return start, end


def _research_window_metadata(start, end):
    return {
        "calendar_timezone": RESEARCH_CALENDAR_TIMEZONE,
        "from_inclusive": start.isoformat(),
        "to_exclusive": end.isoformat(),
    }
