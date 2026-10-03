"""Live re-check (spec 8.5): re-fetch NPCI, ledger and merchant right before any action and compare
with the evidence the decision used."""
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.domain import EvidenceBundle
from app.engine import audit
from app.mock.sources import Sources


@dataclass
class RecheckResult:
    changed: bool
    changed_sources: list[str] = field(default_factory=list)


def live_recheck(db: Session, sources: Sources, case_id: str, b: EvidenceBundle, before: str,
                 now: datetime) -> RecheckResult:
    ref = b.txn.upi_ref
    fresh = {
        "NPCI": sources.evidence.npci_status(ref),
        "BANK_LEDGER": sources.evidence.bank_ledger(ref),
        "MERCHANT": sources.evidence.merchant_credit(ref),
    }
    used = {"NPCI": b.npci, "BANK_LEDGER": b.ledger, "MERCHANT": b.merchant}
    changed = [k for k in fresh if fresh[k].model_dump() != used[k].model_dump()]
    if changed:
        audit.log(db, case_id, now, "RECHECK_CHANGED", {
            "before_action": before, "changed_sources": changed,
            "was": {k: used[k].model_dump(mode="json") for k in changed},
            "now": {k: fresh[k].model_dump(mode="json") for k in changed},
        })
    else:
        audit.log(db, case_id, now, "RECHECK_PASSED", {"before_action": before})
    return RecheckResult(changed=bool(changed), changed_sources=changed)
