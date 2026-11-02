"""Injectable clock.

All deadline/overdue logic reads time from here so tests can pin "now"
deterministically instead of depending on the wall clock.
"""
from datetime import date, datetime, timezone

_override: datetime | None = None


def set_now(value: datetime | None) -> None:
    """Pin the clock (tests). Pass None to return to real time."""
    global _override
    _override = value


def now() -> datetime:
    if _override is not None:
        return _override
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return now().date()
