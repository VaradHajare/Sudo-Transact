"""Cases: open (mic tap), briefing, voice turns, chat history, retry confirm, manual dispute."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app import clock
from app.api.v1.auth import current_user
from app.api.v1.idempotency import run_idempotent
from app.api.v1.views import activity_view, case_view, message_view, messages_view, txn_view
from app.config import Settings
from app.conversation.turn import TurnResult, briefing_items, handle_turn
from app.deps import get_app_settings, get_db
from app.engine import audit
from app.engine.pipeline import process_transaction
from app.models import Case, Dispute, Message, Transaction, User

router = APIRouter()


def own_case(db: Session, user: User, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if case is None or case.user_id != user.id:
        raise HTTPException(404, "case not found")
    return case


# ------------------------------------------------------------------ open (user tapped the mic on a payment)
class OpenIn(BaseModel):
    txn_id: str


@router.post("/cases/open")
def open_case(body: OpenIn, user: User = Depends(current_user), db: Session = Depends(get_db),
              settings: Settings = Depends(get_app_settings)):
    """Bound to the payment on screen. Returns the prepared case; assembles it on demand if needed."""
    txn = db.get(Transaction, body.txn_id)
    if txn is None or txn.payer_user_id != user.id:
        raise HTTPException(404, "transaction not found")
    if txn.direction != "OUT":
        raise HTTPException(422, "only outgoing payments can be opened as a case")
    existed = db.query(Case).filter(Case.txn_id == txn.id).count() > 0
    case = process_transaction(db, settings, txn.id, "USER_OPEN").case
    briefing = briefing_items(db, user.id, case.id, case.language)
    had_update = case.has_unseen_update
    case.has_unseen_update = False  # the user is looking at it now
    audit.log(db, case.id, clock.now(db), "CASE_OPENED_BY_USER", {"prepared": existed, "had_update": had_update},
              actor="USER")
    db.commit()
    return {"case": case_view(db, case), "transaction": txn_view(db, txn, case),
            "messages": messages_view(db, case.id), "briefing": briefing, "prepared_in_background": existed}


@router.get("/briefing")
def get_briefing(exclude_case_id: str | None = None, lang: str | None = None, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    return {"items": briefing_items(db, user.id, exclude_case_id, lang or user.language_pref)}


@router.get("/cases/{case_id}")
def get_case(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = own_case(db, user, case_id)
    return {**case_view(db, case), "transaction": txn_view(db, db.get(Transaction, case.txn_id), case),
            "timeline": [{"ts": e["ts"], "event": e["event"]} for e in activity_view(db, case.id)]}


@router.get("/cases/{case_id}/messages")
def get_messages(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_case(db, user, case_id)
    return {"case_id": case_id, "messages": messages_view(db, case_id)}


@router.get("/cases/{case_id}/activity")
def get_activity(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_case(db, user, case_id)
    return {"case_id": case_id, "events": activity_view(db, case_id)}


# ------------------------------------------------------------------ voice turn
class TurnIn(BaseModel):
    case_id: str
    text: str | None = None
    chip_id: str | None = None
    lang: str | None = None


def turn_response(db: Session, r: TurnResult) -> dict:
    case = r.case
    return {
        "case_id": case.id, "decision": case.decision, "rule": case.rule_id, "situation": r.situation,
        "intent": r.intent, "lang": r.lang, "user_text": r.user_text,
        "speak": {"lang": r.lang, "text": r.reply, "audio_url": None, "facts": r.facts},
        "chips": r.chips, "actions": r.actions, "case": case_view(db, case),
        "messages": [message_view(db.get(Message, r.user_message_id)), message_view(db.get(Message, r.agent_message_id))],
    }


@router.post("/voice/turn")
async def voice_turn(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                     settings: Settings = Depends(get_app_settings),
                     idempotency_key: str | None = Header(default=None)):
    """JSON {case_id, text | chip_id, lang?}. Multipart with an `audio` file needs STT (step 7)."""
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        if form.get("audio") is not None and not settings.STT_ENABLED:
            raise HTTPException(422, "stt_disabled: send text instead (STT_ENABLED=false)")
        raw = {k: form.get(k) for k in ("case_id", "text", "chip_id", "lang") if form.get(k) is not None}
    else:
        raw = await request.json()
    try:
        body = TurnIn.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False)) from None
    if not (body.text and body.text.strip()) and not body.chip_id:
        raise HTTPException(422, "send text or chip_id")
    case = own_case(db, user, body.case_id)

    def run():
        r = handle_turn(db, settings, case, text=body.text, chip_id=body.chip_id, lang_hint=body.lang)
        return 200, turn_response(db, r)

    return run_idempotent(db, user.id, idempotency_key, "/v1/voice/turn", body.model_dump(), run)


# ------------------------------------------------------------------ retry confirm (chip tap / "yes")
@router.post("/cases/{case_id}/retry/confirm")
def retry_confirm(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db),
                  settings: Settings = Depends(get_app_settings), idempotency_key: str | None = Header(default=None)):
    """Live re-check + full retry gate. Returns the pay-screen payload only if everything passes."""
    case = own_case(db, user, case_id)

    def run():
        r = handle_turn(db, settings, case, chip_id="retry")
        pay = next((a["payload"] for a in r.actions if a["type"] == "OPEN_PAY_SCREEN"), None)
        return 200, {"ok": pay is not None, "pay_screen": pay, **turn_response(db, r)}

    return run_idempotent(db, user.id, idempotency_key, f"/v1/cases/{case_id}/retry/confirm", {}, run)


# ------------------------------------------------------------------ manual dispute trigger
@router.post("/cases/{case_id}/dispute")
def manual_dispute(case_id: str, user: User = Depends(current_user), db: Session = Depends(get_db),
                   settings: Settings = Depends(get_app_settings), idempotency_key: str | None = Header(default=None)):
    """Normally the scheduler does this. The rules still decide: no dispute unless they say so."""
    case = own_case(db, user, case_id)

    def run():
        process_transaction(db, settings, case.txn_id, "MANUAL")
        dispute = db.query(Dispute).filter(Dispute.case_id == case.id).first()
        if dispute is None:
            return 409, {"detail": "the rules do not allow a dispute for this case now",
                         "decision": case.decision, "rule": case.rule_id, "case": case_view(db, case)}
        return 200, {"raised": True, "case": case_view(db, case)}

    return run_idempotent(db, user.id, idempotency_key, f"/v1/cases/{case_id}/dispute", {}, run)
