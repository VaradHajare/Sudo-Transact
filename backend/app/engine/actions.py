"""Carry out a decision: update case state, raise disputes, schedule jobs, escalate, notify.

Only the decision engine chooses the action; this module executes it idempotently.
"""
import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import clock, providers
from app.config import Settings
from app.conversation import templates
from app.conversation.facts import case_facts, case_situation
from app.domain import Action, Decision, Diagnosis, EvidenceBundle
from app.engine import audit
from app.mock.sources import Sources
from app.models import Case, CompensationClaim, Dispute, EvidenceItem, Job, Message, Retry

STATE_FOR = {
    Action.WAIT: "WAITING", Action.OFFER_RETRY: "RETRY_OFFERED", Action.RAISE_DISPUTE: "DISPUTED",
    Action.CLOSE: "CLOSED", Action.ESCALATE: "ESCALATED",
}
TERMINAL_STATES = {"CLOSED", "RESOLVED", "ESCALATED", "REVIEWED"}


def save_evidence(db: Session, case: Case, b: EvidenceBundle, now: datetime) -> None:
    """Store evidence rows when the external state changed (or the first time)."""
    fp = b.fingerprint()
    if case.evidence_fingerprint == fp and case.evidence_json:
        return
    rows = {
        "PAYTM_RECORD": (b.txn.status, b.txn.model_dump(mode="json")),
        "NPCI": (str(b.npci.status), b.npci.model_dump(mode="json")),
        "BANK_LEDGER": (str(b.ledger.state), b.ledger.model_dump(mode="json")),
        "MERCHANT": ("CREDITED" if b.merchant.credited else "NOT_CREDITED", b.merchant.model_dump(mode="json")),
    }
    for source, (status, detail) in rows.items():
        db.add(EvidenceItem(txn_id=b.txn.id, case_id=case.id, source=source, status=status,
                            detail_json=json.dumps(detail), observed_at=now))


def schedule_job(db: Session, kind: str, case_id: str, run_at: datetime, now: datetime) -> None:
    db.query(Job).filter(Job.case_id == case_id, Job.status == "QUEUED").update({"status": "CANCELLED"})
    db.add(Job(kind=kind, case_id=case_id, run_at=run_at, created_at=now))


def raise_dispute(db: Session, sources: Sources, settings: Settings, case: Case, b: EvidenceBundle,
                  dec: Decision, now: datetime) -> None:
    existing = db.query(Dispute).filter(Dispute.case_id == case.id, Dispute.kind == dec.dispute_kind).one_or_none()
    if existing:
        _update_compensation(db, settings, case, dec, now)
        return
    amount = b.ledger.amount_paise or b.txn.amount_paise
    ref = sources.disputes.raise_dispute(b.txn.upi_ref, dec.dispute_kind, amount, now)
    db.add(Dispute(case_id=case.id, kind=dec.dispute_kind, mock_udir_ref=ref, amount_paise=amount, raised_at=now))
    audit.log(db, case.id, now, "DISPUTE_RAISED", {"kind": dec.dispute_kind, "udir_ref": ref, "amount_paise": amount})
    if dec.compensation:
        comp = settings.compensation_per_day_paise * dec.days_late
        db.add(CompensationClaim(case_id=case.id, days_late=dec.days_late, amount_paise=comp, created_at=now))
        audit.log(db, case.id, now, "COMPENSATION_FLAGGED",
                  {"days_late": dec.days_late, "amount_paise": comp,
                   "per_day_paise": settings.compensation_per_day_paise})
    db.flush()


def _update_compensation(db: Session, settings: Settings, case: Case, dec: Decision, now: datetime) -> None:
    """Still not reversed after the dispute: compensation keeps growing per day late (spec 6.7)."""
    if not dec.compensation:
        return
    comp = db.query(CompensationClaim).filter(CompensationClaim.case_id == case.id).one_or_none()
    if comp is None or dec.days_late <= comp.days_late:
        return
    before = comp.amount_paise
    comp.days_late = dec.days_late
    comp.amount_paise = settings.compensation_per_day_paise * dec.days_late
    audit.log(db, case.id, now, "COMPENSATION_UPDATED",
              {"days_late": comp.days_late, "amount_paise": comp.amount_paise, "was_paise": before})


RECOMMENDATIONS = {
    "NPCI_SUCCESS_NO_DEBIT": "Confirm with the issuer bank whether the debit happened before any retry or dispute.",
    "CREDIT_WITHOUT_DEBIT": "Ask the merchant's bank to verify the credit; check the issuer ledger for a late debit.",
    "RECORD_NPCI_MISMATCH": "Reconcile the Paytm record with NPCI before telling the user anything final.",
    "NPCI_FAILED_BUT_CREDITED": "Check whether the merchant credit belongs to this payment.",
    "REVERSED_BUT_CREDITED": "Possible double benefit: verify the reversal and the merchant credit.",
    "LEDGER_AMOUNT_MISMATCH": "Verify the debited amount with the issuer bank.",
    "CLAIM_AMOUNT_MISMATCH": "The user's stated amount differs from the record: verify the claim before any action.",
    "CLAIM_PAYEE_MISMATCH": "The user's stated payee differs from the record: verify the claim before any action.",
    "REPEAT_CLAIMS": "Repeat-claim pattern: review the user's recent claims.",
}


def build_case_file(db: Session, case: Case, b: EvidenceBundle | None, d: Diagnosis | None,
                    dec: Decision | None, reason: str, now: datetime) -> dict:
    from app.models import Transaction

    txn = db.get(Transaction, case.txn_id)
    issues = (b.conflicts + b.suspicious) if b else []
    recs = [RECOMMENDATIONS[c.code] for c in issues if c.code in RECOMMENDATIONS]
    if reason == "USER_REQUESTED":
        recs.insert(0, "User asked for a human. Reply in the chat; the agent's current answer is in `agent_answer`.")
    if not recs:
        recs = ["Classify manually; no automatic action was safe."]
    when = clock.to_ist(txn.initiated_at).strftime("%d %b %H:%M IST")
    summary = (f"₹{templates.inr(txn.amount_paise)} to {txn.payee_name} ({txn.payee_vpa}) on {when}. "
               f"Paytm record {txn.status}"
               + (f"; NPCI {b.npci.status}; ledger {b.ledger.state}; merchant "
                  f"{'credited' if b.merchant.credited else 'not credited'}" if b else "")
               + (f". Issues: {', '.join(c.code for c in issues)}" if issues else "")
               + f". Escalated because: {reason}.")
    facts = case_facts(db, case)
    return {
        "case_id": case.id, "txn_id": txn.id, "upi_ref": txn.upi_ref, "user_id": case.user_id,
        "escalated_at": clock.iso_ist(now), "reason": reason, "summary": summary,
        "evidence": {
            "paytm_record": b.txn.model_dump(mode="json") if b else None,
            "npci": b.npci.model_dump(mode="json") if b else None,
            "bank_ledger": b.ledger.model_dump(mode="json") if b else None,
            "merchant": b.merchant.model_dump(mode="json") if b else None,
        },
        "conflicts": [c.model_dump() for c in (b.conflicts if b else [])],
        "suspicious": [c.model_dump() for c in (b.suspicious if b else [])],
        "claims": [c.model_dump(mode="json") for c in (b.claims if b else [])],
        "diagnosis": d.model_dump(mode="json") if d else None,
        "rule_trace": dec.trace if dec else [],
        "llm_reasoning": None,
        "recommended_actions": recs,
        "agent_answer": templates.status_text(case_situation(case), facts, "en") if case.class_ else None,
        "timeline": [{"ts": clock.iso_ist(e.ts), "event": e.event_type} for e in audit.events(db, case.id)],
    }


def escalate(db: Session, case: Case, reason: str, now: datetime, b: EvidenceBundle | None = None,
             d: Diagnosis | None = None, dec: Decision | None = None, actor: str = "SYSTEM") -> None:
    if case.state == "ESCALATED":
        return
    case.escalation_reason = reason
    case.case_file_json = json.dumps(build_case_file(db, case, b, d, dec, reason, now), ensure_ascii=False)
    case.state = "ESCALATED"
    case.updated_at = now
    db.query(Job).filter(Job.case_id == case.id, Job.status == "QUEUED").update({"status": "CANCELLED"})
    audit.log(db, case.id, now, "ESCALATED", {"reason": reason}, actor=actor)
    p = providers.current()
    if p.llm and p.settings and p.settings.LLM_ENABLED and p.settings.LLM_CASE_SUMMARY_ENABLED:
        # The reviewer's LLM summary is written in the background so the user's reply isn't delayed.
        db.add(Job(kind="CASE_SUMMARY", case_id=case.id, run_at=now, created_at=now))


def add_agent_message(db: Session, case: Case, text: str, now: datetime, kind: str = "reply",
                      chips: list | None = None, actions: list | None = None, facts: dict | None = None,
                      intent: str | None = None) -> Message:
    msg = Message(case_id=case.id, ts=now, role="agent", kind=kind, text=text, lang=case.language,
                  intent=intent, decision=case.decision, chips_json=json.dumps(chips or [], ensure_ascii=False),
                  actions_json=json.dumps(actions or [], ensure_ascii=False),
                  facts_json=json.dumps(facts or {}, default=str))
    db.add(msg)
    db.flush()
    return msg


def notify(db: Session, case: Case, now: datetime) -> None:
    """NOTIFY (spec 6.10): new agent message at the bottom of this case's chat + unseen badge."""
    sit = case_situation(case)
    if sit not in templates.UPDATE_SITUATIONS:
        return
    facts = case_facts(db, case)
    text = templates.status_text(sit, facts, case.language)
    add_agent_message(db, case, text, now, kind="update", chips=templates.chips(sit, facts, case.language),
                      facts=facts.model_dump(mode="json"))
    case.has_unseen_update = True
    audit.log(db, case.id, now, "NOTIFIED", {"situation": sit})


def apply_decision(db: Session, sources: Sources, settings: Settings, case: Case, b: EvidenceBundle,
                   d: Diagnosis, dec: Decision, trigger: str, now: datetime) -> None:
    prev_state = case.state
    save_evidence(db, case, b, now)
    case.class_ = str(d.case_class)
    case.confidence = d.confidence
    case.decision = str(dec.action)
    case.rule_id = dec.rule
    case.deadline_ts = dec.deadline_ts or case.deadline_ts
    case.next_check_at = dec.next_check_at
    case.evidence_fingerprint = b.fingerprint()
    case.evidence_json = json.dumps({
        "npci": b.npci.model_dump(mode="json"), "ledger": b.ledger.model_dump(mode="json"),
        "merchant": b.merchant.model_dump(mode="json")})
    case.conflicts_json = json.dumps([c.model_dump() for c in b.conflicts + b.suspicious])
    case.updated_at = now

    if dec.action == Action.ESCALATE:
        escalate(db, case, f"rule {dec.rule}: " + dec.trace[-1].split(": ", 1)[-1], now, b, d, dec)
        return
    if dec.action == Action.WAIT and dec.next_check_at:
        schedule_job(db, "SLA_DEADLINE" if dec.rule == "5" else "RECHECK_CASE", case.id, dec.next_check_at, now)
    if dec.action == Action.OFFER_RETRY:
        open_offer = db.query(Retry).filter(Retry.case_id == case.id, Retry.accepted.is_(None)).first()
        if open_offer is None:
            db.add(Retry(case_id=case.id, offered_at=now))
            audit.log(db, case.id, now, "RETRY_OFFERED", {})
    if dec.action == Action.RAISE_DISPUTE:
        raise_dispute(db, sources, settings, case, b, dec, now)
        schedule_job(db, "DISPUTE_FOLLOWUP", case.id, now + timedelta(hours=settings.DISPUTE_FOLLOWUP_HOURS), now)
    if dec.action == Action.CLOSE:
        case.closed_at = now

    case.state = STATE_FOR[dec.action]
    db.flush()
    if dec.notify and case.state != prev_state and trigger != "USER_TURN":
        notify(db, case, now)
