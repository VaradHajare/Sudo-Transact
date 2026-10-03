"""JSON shapes returned by /v1. Transactions use the web UI's camelCase field names."""
import json

from sqlalchemy.orm import Session

from app import clock
from app.conversation import templates
from app.conversation.facts import case_facts, case_situation
from app.engine import audit
from app.models import Case, CompensationClaim, Dispute, Message, Transaction

NEXT_ACTION = {
    "RETRY_OFFER": "You can safely pay again",
    "PRE_DEBIT_WAIT": "Wait; don't pay again yet",
    "PENDING": "Wait; don't pay again yet",
    "BANK_DOWN": "Try again later",
    "DEBIT_WAIT": "Wait for the automatic refund",
    "DISPUTED": "Complaint raised; nothing to do",
    "DUPLICATE_DISPUTED": "Complaint raised; nothing to do",
    "REVERSED": "Nothing to do",
    "SUCCEEDED": "Nothing to do",
    "ESCALATED": "A human expert will reply here",
    "ESCALATED_USER": "A human expert will reply here",
    "RESOLVED_BY_RETRY": "Nothing to do",
}


def case_badge(db: Session, case: Case | None) -> dict | None:
    if case is None or case.class_ is None:
        return None
    sit = case_situation(case)
    return {"id": case.id, "state": case.state, "situation": sit, "hasUpdate": case.has_unseen_update,
            "statusLine": templates.status_line(sit, case_facts(db, case))}


def txn_view(db: Session, t: Transaction, case: Case | None = None) -> dict:
    if case is None:
        case = db.query(Case).filter(Case.txn_id == t.id).one_or_none()
    return {
        "id": t.id, "payeeName": t.payee_name, "payeeVpa": t.payee_vpa, "amountPaise": t.amount_paise,
        "status": t.status, "debited": t.debited, "timestamp": clock.iso_ist(t.initiated_at), "note": t.note,
        "direction": t.direction, "category": t.category, "railLabel": t.rail_label, "upiRef": t.upi_ref,
        "failureReason": t.failure_reason, "case": case_badge(db, case),
    }


def case_view(db: Session, case: Case) -> dict:
    txn = db.get(Transaction, case.txn_id)
    sit = case_situation(case) if case.class_ else None
    facts = case_facts(db, case)
    dispute = db.query(Dispute).filter(Dispute.case_id == case.id).order_by(Dispute.id.desc()).first()
    comp = db.query(CompensationClaim).filter(CompensationClaim.case_id == case.id).one_or_none()
    return {
        "id": case.id, "txn_id": case.txn_id, "state": case.state, "class": case.class_,
        "decision": case.decision, "rule": case.rule_id, "situation": sit, "language": case.language,
        "has_unseen_update": case.has_unseen_update,
        "status_line": templates.status_line(sit, facts) if sit else None,
        "next_action": NEXT_ACTION.get(sit) if sit else None,
        "expected_by": clock.to_ist(case.deadline_ts).date().isoformat() if case.deadline_ts else None,
        "deadline": clock.iso_ist(case.deadline_ts),
        "dispute": {"ref": dispute.mock_udir_ref, "kind": dispute.kind, "amount_paise": dispute.amount_paise,
                    "raised_at": clock.iso_ist(dispute.raised_at), "status": dispute.status} if dispute else None,
        "compensation": {"amount_paise": comp.amount_paise, "days_late": comp.days_late,
                         "status": comp.status} if comp else None,
        "conflicts": json.loads(case.conflicts_json or "[]"),
        "card": {"payeeName": txn.payee_name, "payeeVpa": txn.payee_vpa, "amountPaise": txn.amount_paise,
                 "status": txn.status, "timestamp": clock.iso_ist(txn.initiated_at),
                 "statusLine": templates.status_line(sit, facts) if sit else None,
                 "nextAction": NEXT_ACTION.get(sit) if sit else None,
                 "expectedBy": clock.to_ist(case.deadline_ts).date().isoformat() if case.deadline_ts else None},
        "created_at": clock.iso_ist(case.created_at), "updated_at": clock.iso_ist(case.updated_at),
    }


def message_view(m: Message) -> dict:
    return {"id": m.id, "role": m.role, "kind": m.kind, "text": m.text, "lang": m.lang,
            "ts": clock.iso_ist(m.ts), "chips": json.loads(m.chips_json or "[]"),
            "actions": json.loads(m.actions_json or "[]"), "audio_url": m.audio_url}


def messages_view(db: Session, case_id: str) -> list[dict]:
    rows = db.query(Message).filter(Message.case_id == case_id).order_by(Message.id).all()
    return [message_view(m) for m in rows]


def activity_view(db: Session, case_id: str) -> list[dict]:
    return [{"id": e.id, "ts": clock.iso_ist(e.ts), "actor": e.actor, "event": e.event_type,
             "payload": json.loads(e.payload_json or "{}")} for e in audit.events(db, case_id)]
