"""One conversation turn (text now; audio after STT is enabled in step 7).

user text -> language + intent + claims -> refresh the case through the pipeline (rules decide)
-> reply from templates (facts filled from the decision) -> number-check -> store both messages.
"""
import json
import secrets
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import clock
from app.config import Settings
from app import providers
from app.conversation import llm_tasks, templates
from app.conversation.facts import case_facts, case_situation
from app.conversation.intents import detect_intent_ex, detect_language, extract_amount_paise, redact
from app.providers.sarvam import STTResult
from app.domain import Claim
from app.engine import audit
from app.engine.actions import add_agent_message, escalate
from app.engine.pipeline import confirm_retry, process_transaction
from app.models import Case, Message, Retry, Transaction

CHIP_INTENTS = {"retry": "confirm_retry", "why": "why", "talk_to_human": "talk_to_human",
                "what_if": "what_if", "decline": "decline_retry"}


@dataclass
class TurnResult:
    case: Case
    intent: str
    lang: str
    user_text: str
    reply: str
    situation: str
    facts: dict
    chips: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    user_message_id: int | None = None
    agent_message_id: int | None = None
    audio_url: str | None = None
    stt: STTResult | None = None
    chip_id: str | None = None


def briefing_items(db: Session, user_id: str, exclude_case_id: str | None, lang: str) -> list[dict]:
    """Urgent updates on the user's OTHER cases (spec 4.2 step 4)."""
    rows = (db.query(Case).filter(Case.user_id == user_id, Case.has_unseen_update.is_(True))
            .order_by(Case.updated_at.desc()).all())
    items = []
    for c in rows:
        if c.id == exclude_case_id:
            continue
        sit = case_situation(c)
        text = templates.briefing_text(sit, case_facts(db, c), lang)
        if text:
            items.append({"case_id": c.id, "txn_id": c.txn_id, "situation": sit, "text": text, "lang": lang})
    return items


def _language(text: str | None, lang_hint: str | None, case: Case, stt: STTResult | None) -> str:
    base = lang_hint if lang_hint in templates.LANGS else case.language
    if stt and stt.lang in templates.LANGS and (stt.language_probability or 1.0) >= 0.5:
        return stt.lang  # Sarvam's language ID on the actual speech
    return detect_language(text, base) if text else base


def handle_turn(db: Session, settings: Settings, case: Case, *, text: str | None = None,
                chip_id: str | None = None, lang_hint: str | None = None,
                stt: STTResult | None = None) -> TurnResult:
    now = clock.now(db)
    p = providers.current()
    lang = _language(text, lang_hint, case, stt)
    if chip_id in CHIP_INTENTS:
        intent = CHIP_INTENTS[chip_id]
    else:
        intent, matched = detect_intent_ex(text or "", case.state)
        if not matched and text and p.llm and settings.LLM_ENABLED and settings.LLM_INTENT_ENABLED:
            out, meta = llm_tasks.extract_intent(p.llm, text, case.state == "RETRY_OFFERED")
            audit.log(db, case.id, now, "LLM_INTENT", {  # no user text in the audit log
                "ok": meta.ok, "latency_ms": meta.latency_ms, "error": meta.error,
                "intent": out.intent if out else None, "language": out.language if out else None,
                "confidence": out.confidence if out else None}, actor="AGENT")
            if out and out.confidence >= settings.LLM_MIN_CONFIDENCE:
                intent = out.intent
                if not stt:
                    lang = out.language
    case.language = lang

    # user bubble: what they said, or the chip they tapped
    if chip_id and not text:
        f0 = case_facts(db, case)
        label = templates.CHIP_LABELS[lang].get(chip_id, chip_id).format(**f0.vars(lang))
        user_text = label
    else:
        user_text = redact(text or "")
    first_turn = db.query(Message).filter(Message.case_id == case.id, Message.role == "user").count() == 0
    user_msg = Message(case_id=case.id, ts=now, role="user", text=user_text, lang=lang, intent=intent)
    db.add(user_msg)
    db.flush()
    audit.log(db, case.id, now, "USER_TURN", {"message_id": user_msg.id, "intent": intent, "lang": lang,
                                              "chip": chip_id,
                                              "input": "chip" if chip_id else "voice" if stt else "text"}, actor="USER")

    claims = []
    amount = extract_amount_paise(text or "")
    if amount is not None:
        claims.append(Claim(kind="AMOUNT", value=str(amount), ts=now))

    # Rules decide: refresh the case first (rule 0 / deadlines / new claims).
    out = process_transaction(db, settings, case.txn_id, "USER_TURN", new_claims=claims or None)
    actions: list[dict] = []

    if intent == "talk_to_human":
        already = case.state == "ESCALATED"
        if not already:
            escalate(db, case, "USER_REQUESTED", now, out.bundle, out.diagnosis, out.decision, actor="USER")
        sit = case_situation(case)
        facts = case_facts(db, case)
        reply = (templates.dispute_request_text("ESCALATED", facts, lang) if already
                 else templates.status_text("ESCALATED_USER", facts, lang))
    elif intent == "confirm_retry" and case.state == "RETRY_OFFERED":
        res = confirm_retry(db, settings, case)
        sit, facts = case_situation(case), case_facts(db, case)
        if res.ok:
            reply = templates.retry_text("CONFIRMED", facts, lang)
            actions = [{"type": "OPEN_PAY_SCREEN", "payload": res.payload}]
        elif res.recheck_changed:
            reply = templates.retry_text("BLOCKED", facts, lang) + " " + templates.status_text(sit, facts, lang)
        else:
            reply = templates.retry_text("UNAVAILABLE", facts, lang) + " " + templates.status_text(sit, facts, lang)
    elif intent == "decline_retry" and case.state == "RETRY_OFFERED":
        sit, facts = case_situation(case), case_facts(db, case)
        db.query(Retry).filter(Retry.case_id == case.id, Retry.accepted.is_(None)).update({"accepted": False})
        audit.log(db, case.id, now, "RETRY_DECLINED", {}, actor="USER")
        reply = templates.retry_text("DECLINED", facts, lang)
    else:
        sit, facts = case_situation(case), case_facts(db, case)
        if intent == "why":
            reply = templates.why_text(sit, facts, lang)
        elif intent in ("what_if", "what_should_i_do"):
            reply = templates.what_if_text(sit, facts, lang)
        elif intent == "raise_dispute":
            reply = templates.dispute_request_text(sit, facts, lang)
        elif intent == "repeat":
            last = (db.query(Message).filter(Message.case_id == case.id, Message.role == "agent")
                    .order_by(Message.id.desc()).first())
            reply = last.text if last else templates.status_text(sit, facts, lang)
        else:
            reply = templates.status_text(sit, facts, lang)

    # Optional LLM rephrase. Never for the retry read-back (it must be the exact template).
    if (settings.LLM_ENABLED and settings.LLM_REPHRASE_ENABLED and p.llm and not actions
            and intent != "repeat"):
        new, meta, reason = llm_tasks.rephrase(p.llm, reply, [facts], lang)
        audit.log(db, case.id, now, "LLM_REPHRASE", {"ok": meta.ok, "latency_ms": meta.latency_ms,
                                                     "used": new is not None, "reason": reason}, actor="AGENT")
        if new:
            reply = new

    facts_list = [facts]
    if first_turn:
        brief = briefing_items(db, case.user_id, case.id, lang)
        for item in brief[:2]:
            reply += " " + item["text"]
            facts_list.append(case_facts(db, db.get(Case, item["case_id"])))
    bad = templates.number_check(reply, facts_list, lang)
    if bad:  # last line of defence (templates always pass; the rephrase is checked above too)
        audit.log(db, case.id, now, "NUMBER_CHECK_FAILED", {"numbers": bad})
        reply = templates.status_text(sit, facts, lang)

    chips = [] if actions else templates.chips(sit, facts, lang)
    facts_out = speak_facts(facts, lang)
    agent_msg = add_agent_message(db, case, reply, now, chips=chips, actions=actions, facts=facts_out, intent=intent)
    if settings.TTS_ENABLED and p.sarvam:
        # Synthesized lazily on first GET, so the reply text is never held up by TTS.
        agent_msg.audio_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/v1/audio/{secrets.token_hex(16)}"
    case.has_unseen_update = False
    audit.log(db, case.id, now, "AGENT_REPLIED", {"message_id": agent_msg.id, "situation": sit,
                                                  "decision": case.decision, "rule": case.rule_id,
                                                  "intent": intent, "lang": lang}, actor="AGENT")
    return TurnResult(case=case, intent=intent, lang=lang, user_text=user_text, reply=reply, situation=sit,
                      facts=facts_out, chips=chips, actions=actions, user_message_id=user_msg.id,
                      agent_message_id=agent_msg.id, audio_url=agent_msg.audio_url, stt=stt, chip_id=chip_id)


def speak_facts(f: templates.Facts, lang: str) -> dict:
    out = {"amount": templates.inr(f.amount_paise), "amount_paise": f.amount_paise, "payee": f.payee}
    if f.expected_by:
        out["expected_by"] = clock.to_ist(f.expected_by).date().isoformat()
    if f.dispute_ref:
        out["dispute_ref"] = f.dispute_ref
    if f.compensation_paise:
        out["compensation_paise"] = f.compensation_paise
    return out


def resolve_after_retry_payment(db: Session, case: Case, new_txn: Transaction) -> None:
    """The retried payment succeeded: close the original case and tell the user in its chat."""
    now = clock.now(db)
    retry = (db.query(Retry).filter(Retry.case_id == case.id, Retry.accepted.is_(True))
             .order_by(Retry.id.desc()).first())
    if retry:
        retry.new_txn_id = new_txn.id
    case.state, case.closed_at, case.updated_at = "RESOLVED", now, now
    audit.log(db, case.id, now, "RESOLVED_BY_RETRY", {"new_txn_id": new_txn.id})
    facts = case_facts(db, case)
    add_agent_message(db, case, templates.status_text("RESOLVED_BY_RETRY", facts, case.language), now,
                      kind="update", facts=json.loads(facts.model_dump_json()))
