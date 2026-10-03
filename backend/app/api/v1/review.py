"""Human review console API (escalation queue, decisions, agent activity, evaluation numbers) and
delete-my-data. Prototype: any signed-in demo user can act as the reviewer (no separate login yet)."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import clock
from app.api.v1.auth import current_user
from app.api.v1.idempotency import run_idempotent
from app.api.v1.views import activity_view, case_view
from app.config import REPO_DIR, Settings
from app.conversation import templates
from app.conversation.facts import case_facts
from app.deps import get_app_settings, get_db
from app.engine import audit
from app.engine.actions import add_agent_message
from app.models import Case, CaseEvent, Message, Review, Transaction, User

router = APIRouter()


@router.get("/review/queue")
def review_queue(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.query(Case).filter(Case.state == "ESCALATED").order_by(Case.updated_at.desc()).all()
    return {"cases": [{**case_view(db, c), "case_file": json.loads(c.case_file_json or "null"),
                       "escalation_reason": c.escalation_reason} for c in rows]}


@router.get("/review/cases")
def review_cases(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Every case, most recently active first (by its latest audit event). The console's activity
    panel follows the first one, i.e. whatever the agent is working on right now."""
    latest = dict(db.query(CaseEvent.case_id, func.max(CaseEvent.id)).group_by(CaseEvent.case_id).all())
    rows = db.query(Case).all()
    rows.sort(key=lambda c: latest.get(c.id, 0), reverse=True)
    out = []
    for c in rows:
        txn = db.get(Transaction, c.txn_id)
        out.append({"id": c.id, "txn_id": c.txn_id, "payee": txn.payee_name, "amount_paise": txn.amount_paise,
                    "state": c.state, "class": c.class_, "decision": c.decision, "rule": c.rule_id,
                    "last_event_id": latest.get(c.id)})
    return {"cases": out}


@router.get("/review/cases/{case_id}")
def review_case(case_id: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Reviewer view of one case: state, case file, decisions so far and the agent's activity."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    reviews = db.query(Review).filter(Review.case_id == case_id).order_by(Review.id).all()
    return {"case": case_view(db, case), "case_file": json.loads(case.case_file_json or "null"),
            "escalation_reason": case.escalation_reason,
            "reviews": [{"reviewer": r.reviewer, "decision": r.decision, "notes": r.notes,
                         "decided_at": clock.iso_ist(r.decided_at)} for r in reviews],
            "events": activity_view(db, case_id)}


@router.get("/review/evaluation")
def evaluation(_: User = Depends(current_user)):
    """The latest simulator report (backend/scripts/run_sim.py writes docs/evaluation.json)."""
    path = REPO_DIR / "docs" / "evaluation.json"
    if not path.exists():
        raise HTTPException(404, "no evaluation yet: run backend/scripts/run_sim.py")
    return json.loads(path.read_text(encoding="utf-8"))


class ReviewIn(BaseModel):
    decision: Literal["APPROVE", "REJECT", "REQUEST_INFO"]
    reviewer: str = "reviewer"
    notes: str | None = None


@router.post("/review/{case_id}/decision")
def review_decision(case_id: str, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(current_user),
                    idempotency_key: str | None = Header(default=None)):
    case = db.get(Case, case_id)
    if case is None or case.state != "ESCALATED":
        raise HTTPException(404, "no escalated case with that id")

    def run():
        now = clock.now(db)
        db.add(Review(case_id=case.id, reviewer=body.reviewer, decision=body.decision, notes=body.notes,
                      decided_at=now))
        if body.decision != "REQUEST_INFO":
            case.state, case.updated_at = "REVIEWED", now
        audit.log(db, case.id, now, "REVIEW_DECIDED", body.model_dump(), actor="REVIEWER")
        # NOTIFY (spec 6.10): the outcome appears in that payment's chat, in the user's language.
        facts = case_facts(db, case)
        add_agent_message(db, case, templates.review_text(body.decision, facts, case.language), now, kind="update",
                          facts=facts.model_dump(mode="json"), intent="review")
        case.has_unseen_update = True
        audit.log(db, case.id, now, "NOTIFIED", {"situation": f"REVIEW_{body.decision}"})
        return 200, {"case": case_view(db, case)}

    return run_idempotent(db, user.id, idempotency_key, f"/v1/review/{case_id}/decision", body.model_dump(), run)


@router.delete("/me/data")
def delete_my_data(user: User = Depends(current_user), db: Session = Depends(get_db),
                   settings: Settings = Depends(get_app_settings)):
    """Delete the user's chat transcripts, reply audio and claims. The append-only audit log keeps
    only ids / intents / timings, never the text."""
    now = clock.now(db)
    case_ids = [c.id for c in db.query(Case).filter(Case.user_id == user.id).all()]
    audio_dir = Path(settings.MEDIA_DIR) / "audio"
    for (url,) in db.query(Message.audio_url).filter(Message.case_id.in_(case_ids), Message.audio_url.isnot(None)):
        (audio_dir / f"{url.rsplit('/', 1)[-1]}.wav").unlink(missing_ok=True)
    n = db.query(Message).filter(Message.case_id.in_(case_ids)).delete(synchronize_session=False)
    db.query(Case).filter(Case.id.in_(case_ids)).update({"claims_json": "[]"}, synchronize_session=False)
    for cid in case_ids:
        audit.log(db, cid, now, "USER_DATA_DELETED", {"messages_deleted": True}, actor="USER")
    db.commit()
    return {"deleted_messages": n, "cases": len(case_ids)}
