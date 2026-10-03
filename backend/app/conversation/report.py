"""The failed-payment report sent to the owner (WhatsApp / webhook) once a failed or pending payment's
case is prepared. Built from the same records as the chat's agents; no LLM, nothing invented."""
from sqlalchemy.orm import Session

from app import clock
from app.config import Settings
from app.conversation import investigation, templates
from app.conversation.facts import case_facts, case_situation
from app.models import Case, Transaction


def build(db: Session, settings: Settings, case: Case) -> tuple[str, dict]:
    """Returns (WhatsApp text, webhook JSON). English: it is for the owner, not the customer."""
    txn = db.get(Transaction, case.txn_id)
    agents = investigation.build(db, settings, case, txn, "en", changed_sources=[])
    sit = case_situation(case)
    answer = templates.status_text(sit, case_facts(db, case), "en")
    when = clock.to_ist(txn.initiated_at).strftime("%d %b, %I:%M %p IST")
    urgent = case.decision == "ESCALATE"
    lines = [
        f"{'🔴 *Needs a human*' if urgent else '⚠️ *Payment failed*'} · AI Resolve (prototype, mock data)",
        f"*₹{templates.inr(txn.amount_paise)}* to *{txn.payee_name}* ({txn.payee_vpa})",
        f"{txn.status} · {when} · UPI ref {txn.upi_ref}",
    ]
    if txn.failure_reason:
        lines.append(f"Reason: {txn.failure_reason}")
    lines.append("")
    for a in agents:
        # drop the "checking…" progress lines: the report states findings only
        found = [line for line in a["lines"] if not line.endswith("…")]
        lines.append(f"*{a['name']}:* " + " ".join(found))
    lines += ["", f"*Told the customer:* {answer}", f"Case {case.id} · rule {case.rule_id} · {case.decision}"]
    text = "\n".join(lines)
    payload = {
        "event": "payment_failed", "urgent": urgent, "case_id": case.id, "txn_id": txn.id,
        "upi_ref": txn.upi_ref, "payee_name": txn.payee_name, "payee_vpa": txn.payee_vpa,
        "amount_paise": txn.amount_paise, "status": txn.status, "failure_reason": txn.failure_reason,
        "initiated_at": clock.iso_ist(txn.initiated_at), "class": case.class_, "decision": case.decision,
        "rule": case.rule_id, "situation": sit, "deadline": clock.iso_ist(case.deadline_ts),
        "agents": agents, "customer_answer": answer,
    }
    return text, payload
