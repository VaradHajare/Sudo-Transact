"""Human review queue (escalated cases) and delete-my-data."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import clock
from app.api.v1.auth import current_user
from app.api.v1.idempotency import run_idempotent
from app.api.v1.views import case_view
from app.deps import get_db
from app.engine import audit
from app.models import Case, Message, Review, User

router = APIRouter()


@router.get("/review/queue")
def review_queue(db: Session = Depends(get_db), _: User = Depends(current_user)):
    # Prototype: any signed-in demo user can see the queue (the console has no separate login yet).
    rows = db.query(Case).filter(Case.state == "ESCALATED").order_by(Case.updated_at.desc()).all()
    return {"cases": [{**case_view(db, c), "case_file": json.loads(c.case_file_json or "null"),
                       "escalation_reason": c.escalation_reason} for c in rows]}


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
        return 200, {"case": case_view(db, case)}

    return run_idempotent(db, user.id, idempotency_key, f"/v1/review/{case_id}/decision", body.model_dump(), run)


@router.delete("/me/data")
def delete_my_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the user's chat transcripts and claims. The append-only audit log keeps only ids/intents."""
    now = clock.now(db)
    case_ids = [c.id for c in db.query(Case).filter(Case.user_id == user.id).all()]
    n = db.query(Message).filter(Message.case_id.in_(case_ids)).delete(synchronize_session=False)
    db.query(Case).filter(Case.id.in_(case_ids)).update({"claims_json": "[]"}, synchronize_session=False)
    for cid in case_ids:
        audit.log(db, cid, now, "USER_DATA_DELETED", {"messages_deleted": True}, actor="USER")
    db.commit()
    return {"deleted_messages": n, "cases": len(case_ids)}
