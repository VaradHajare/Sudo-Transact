"""Append-only audit log (case_events). Every rule firing, re-check, voice turn and action is an event."""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import CaseEvent


def log(db: Session, case_id: str, ts: datetime, event_type: str, payload: dict | None = None,
        actor: str = "SYSTEM") -> None:
    db.add(CaseEvent(case_id=case_id, ts=ts, actor=actor, event_type=event_type,
                     payload_json=json.dumps(payload or {}, default=str, ensure_ascii=False)))


def events(db: Session, case_id: str) -> list[CaseEvent]:
    return db.query(CaseEvent).filter(CaseEvent.case_id == case_id).order_by(CaseEvent.id).all()
