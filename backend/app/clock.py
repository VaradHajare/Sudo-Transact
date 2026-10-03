"""Simulated clock. All code asks `now(db)` instead of datetime.now(), so /mock/clock can skip time.

Stored times are naive UTC. India has no DST, so IST is a fixed +05:30 offset.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import ClockState

IST = timezone(timedelta(hours=5, minutes=30))


def real_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_offset(db: Session) -> int:
    row = db.get(ClockState, 1)
    return row.offset_seconds if row else 0


def now(db: Session) -> datetime:
    return real_utcnow() + timedelta(seconds=get_offset(db))


def advance(db: Session, seconds: int) -> datetime:
    row = db.get(ClockState, 1)
    if row is None:
        row = ClockState(id=1, offset_seconds=0)
        db.add(row)
    row.offset_seconds += int(seconds)
    db.flush()
    return now(db)


def reset(db: Session) -> None:
    row = db.get(ClockState, 1)
    if row:
        row.offset_seconds = 0
        db.flush()


def to_ist(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)


def iso_ist(dt: datetime | None) -> str | None:
    return to_ist(dt).isoformat() if dt else None


def ist_to_utc_naive(dt_ist: datetime) -> datetime:
    return dt_ist.astimezone(timezone.utc).replace(tzinfo=None)
