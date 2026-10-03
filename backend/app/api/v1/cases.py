"""Cases: open (mic tap), briefing, voice turns, reply audio, chat history, retry confirm, manual dispute."""
import hashlib
import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app import clock, i18n, providers
from app.providers.sarvam import ProviderError
from app.api.v1.auth import current_user
from app.api.v1.idempotency import run_idempotent
from app.api.v1.views import activity_view, case_view, message_view, messages_view, txn_view
from app.config import Settings
from app.conversation.facts import case_situation
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
    # The payment just failed in front of the user (team decision 3): the chat opens with the
    # agent's detailed investigation (three agents) and its conclusion, in the UI language.
    investigate: bool = False
    lang: str | None = None


@router.post("/cases/open")
def open_case(body: OpenIn, user: User = Depends(current_user), db: Session = Depends(get_db),
              settings: Settings = Depends(get_app_settings)):
    """Bound to the payment on screen. Returns the prepared case; assembles it on demand if needed."""
    txn = db.get(Transaction, body.txn_id)
    if txn is None or txn.payer_user_id != user.id:
        raise HTTPException(404, "transaction not found")
    if txn.direction != "OUT":
        raise HTTPException(422, "only outgoing payments can be opened as a case")
    prior = db.query(Case).filter(Case.txn_id == txn.id).one_or_none()
    existed = prior is not None
    evidence_before = json.loads(prior.evidence_json or "{}") if prior else {}
    investigate = body.investigate and txn.status in ("FAILED", "PENDING") and not (
        prior and db.query(Message).filter(Message.case_id == prior.id).count())
    # live re-fetch + re-decide (the investigation's conclusion replaces any update message)
    case = process_transaction(db, settings, txn.id, "USER_INVESTIGATE" if investigate else "USER_OPEN").case
    investigation = _investigate(db, settings, case, txn, body.lang, evidence_before) if investigate else None
    briefing = briefing_items(db, user.id, case.id, case.language)
    had_update = case.has_unseen_update
    case.has_unseen_update = False  # the user is looking at it now
    audit.log(db, case.id, clock.now(db), "CASE_OPENED_BY_USER", {"prepared": existed, "had_update": had_update},
              actor="USER")
    db.commit()
    return {"case": case_view(db, case), "transaction": txn_view(db, txn, case),
            "messages": messages_view(db, case.id), "briefing": briefing, "prepared_in_background": existed,
            "investigation": investigation}


def _investigate(db: Session, settings: Settings, case: Case, txn: Transaction, lang: str | None,
                 evidence_before: dict) -> dict:
    """Two agent messages, once per case: the intro ("…failed. I'm running a detailed investigation")
    carrying the three agents' steps, then the conclusion (the normal status answer) with its chips."""
    from app.conversation import investigation, templates
    from app.conversation.facts import case_facts
    from app.conversation.turn import speak_facts
    from app.engine.actions import add_agent_message

    lang = i18n.ui_lang() or (lang if lang in templates.LANGS else case.language)
    case.language = lang
    evidence_now = json.loads(case.evidence_json or "{}")
    changed = [src for key, src in (("npci", "NPCI"), ("ledger", "BANK_LEDGER"), ("merchant", "MERCHANT"))
               if evidence_before and evidence_before.get(key) != evidence_now.get(key)]
    agents = investigation.build(db, settings, case, txn, lang, changed)
    facts = case_facts(db, case)
    now = clock.now(db)
    tts = settings.TTS_ENABLED and providers.current().sarvam
    audio = (lambda: f"{settings.PUBLIC_BASE_URL.rstrip('/')}/v1/audio/{secrets.token_hex(16)}") if tts else (lambda: None)
    intro = add_agent_message(db, case, investigation.intro_text(txn, lang), now, intent="investigation",
                              actions=[{"type": "INVESTIGATION", "agents": agents}],
                              facts=speak_facts(facts, lang))
    intro.audio_url = audio()
    sit = case_situation(case)
    conclusion = add_agent_message(db, case, investigation.conclusion_text(db, case, lang), now, intent="conclusion",
                                   chips=templates.chips(sit, facts, lang), facts=speak_facts(facts, lang))
    conclusion.audio_url = audio()
    audit.log(db, case.id, now, "INVESTIGATION_SHOWN", {"lang": lang, "agents": [a["id"] for a in agents],
                                                        "changed_sources": changed, "situation": sit}, actor="AGENT")
    return {"intro": message_view(intro), "agents": agents, "conclusion": message_view(conclusion)}


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
        "input": "voice" if r.stt else "chip" if r.chip_id else "text",
        "stt": {"language_code": r.stt.language_code, "language_probability": r.stt.language_probability,
                "latency_ms": r.stt.latency_ms} if r.stt else None,
        "speak": {"lang": r.lang, "text": r.reply, "audio_url": r.audio_url, "facts": r.facts},
        "chips": r.chips, "actions": r.actions, "end_conversation": r.end_conversation,
        "case": case_view(db, case),
        "messages": [message_view(db.get(Message, r.user_message_id)), message_view(db.get(Message, r.agent_message_id))],
    }


@router.post("/voice/turn")
async def voice_turn(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db),
                     settings: Settings = Depends(get_app_settings),
                     idempotency_key: str | None = Header(default=None)):
    """JSON {case_id, text | chip_id, lang?}, or multipart {case_id, audio, lang?} (Sarvam STT)."""
    audio: bytes | None = None
    audio_type = None
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        upload = form.get("audio")
        if upload is not None:
            if not (settings.STT_ENABLED and providers.current().sarvam):
                raise HTTPException(422, "stt_disabled: send text instead (STT_ENABLED=false)")
            audio = await upload.read()
            audio_type = upload.content_type
            if not audio:
                raise HTTPException(422, "empty audio")
            if len(audio) > settings.STT_MAX_AUDIO_BYTES:
                raise HTTPException(413, "audio too large")
        raw = {k: form.get(k) for k in ("case_id", "text", "chip_id", "lang") if isinstance(form.get(k), str)}
    else:
        raw = await request.json()
    try:
        body = TurnIn.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False)) from None
    if audio is None and not (body.text and body.text.strip()) and not body.chip_id:
        raise HTTPException(422, "send text, chip_id or audio")
    case = own_case(db, user, body.case_id)
    req = body.model_dump()
    if audio is not None:
        req["audio_sha256"] = hashlib.sha256(audio).hexdigest()

    def run():
        stt = None
        text = body.text
        if audio is not None:
            try:
                stt = providers.current().sarvam.stt(audio, audio_type, "speech.webm")
            except ProviderError as e:
                if e.unusable_audio:  # empty / too-short clip: same as hearing nothing
                    audit.log(db, case.id, clock.now(db), "STT", {"bytes": len(audio), "empty": True,
                                                                  "rejected": True}, actor="AGENT")
                    db.commit()
                    return 422, {"detail": "no_speech"}
                return 502, {"detail": "stt_failed", "error": str(e)[:200]}
            audit.log(db, case.id, clock.now(db), "STT", {  # no transcript in the audit log
                "latency_ms": stt.latency_ms, "language_code": stt.language_code,
                "language_probability": stt.language_probability, "bytes": len(audio),
                "empty": not stt.transcript}, actor="AGENT")
            if not stt.transcript:
                db.commit()
                return 422, {"detail": "no_speech"}
            text = stt.transcript
        r = handle_turn(db, settings, case, text=text, chip_id=None if stt else body.chip_id,
                        lang_hint=body.lang, stt=stt)
        return 200, turn_response(db, r)

    # STT + LLM calls block: keep them off the event loop.
    return await run_in_threadpool(run_idempotent, db, user.id, idempotency_key, "/v1/voice/turn", req, run)


# ------------------------------------------------------------------ reply audio (TTS)
@router.get("/audio/{token}")
def reply_audio(token: str, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    """Synthesized on first request, then cached on disk. No bearer header (an <audio> element
    can't send one): the 128-bit token in the URL is the capability."""
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise HTTPException(404)
    path = Path(settings.MEDIA_DIR) / "audio" / f"{token}.wav"
    if not path.exists():
        msg = db.query(Message).filter(Message.audio_url.like(f"%/v1/audio/{token}")).first()
        sarvam = providers.current().sarvam
        if msg is None:
            raise HTTPException(404)
        if not (settings.TTS_ENABLED and sarvam):
            raise HTTPException(503, "tts_disabled")
        try:
            wav = sarvam.tts(msg.text, msg.lang)
        except ProviderError as e:
            raise HTTPException(502, f"tts_failed: {str(e)[:200]}") from None
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_bytes(wav)
        tmp.replace(path)
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


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
