"""Build template facts for a case from the DB (decision engine output + records)."""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.conversation import templates
from app.models import Case, CompensationClaim, Dispute, Transaction


def case_facts(db: Session, case: Case) -> templates.Facts:
    txn = db.get(Transaction, case.txn_id)
    dispute = (db.query(Dispute).filter(Dispute.case_id == case.id).order_by(Dispute.id.desc()).first())
    comp = db.query(CompensationClaim).filter(CompensationClaim.case_id == case.id).one_or_none()
    reversed_at = None
    if case.evidence_json:
        raw = json.loads(case.evidence_json).get("ledger", {}).get("reversed_at")
        reversed_at = datetime.fromisoformat(raw) if raw else None
    return templates.Facts(
        amount_paise=txn.amount_paise, payee=txn.payee_name, expected_by=case.deadline_ts,
        dispute_ref=dispute.mock_udir_ref if dispute else None,
        compensation_paise=comp.amount_paise if comp else None,
        days_late=comp.days_late if comp else None, reversed_at=reversed_at,
    )


def case_situation(case: Case) -> str:
    return templates.situation(case.class_, case.decision, case.state, case.escalation_reason)
