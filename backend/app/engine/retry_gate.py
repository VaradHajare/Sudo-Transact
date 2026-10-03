"""Safe-retry gate (spec 8.4). Every condition is reported separately so the trace shows why.

Phases: when the decision engine considers OFFERING a retry, G6 (live re-check) and G7 (user
confirmation) are not known yet and are passed as None. Before returning the pay-screen payload,
all ten checks must be True.
"""
import re
from datetime import datetime, timedelta

from app.config import Settings
from app.domain import CaseClass, Diagnosis, EvidenceBundle, GateCheck, GateResult, RetryHistory

PRE_DEBIT = {CaseClass.F1_DECLINED_PRE_DEBIT, CaseClass.F2_TIMEOUT_PRE_DEBIT}
TRUSTED_PAYEE_SOURCES = {"PAYTM_RECORD", "QR"}
VPA_RE = re.compile(r"^[A-Za-z0-9._\-]{2,256}@[A-Za-z][A-Za-z0-9]{1,64}$")

# Conditions that only mean "not yet" -> rule 7b WAIT instead of escalating.
SOFT_CONDITIONS = {"G2_NPCI_FINAL_FAILED", "G2_PENDING_WINDOW", "G5_COOLDOWN"}


def evaluate_gate(b: EvidenceBundle, d: Diagnosis, now: datetime, settings: Settings, history: RetryHistory,
                  *, recheck_passed: bool | None = None, user_confirmed: bool | None = None) -> GateResult:
    t, n, l = b.txn, b.npci, b.ledger
    age = now - t.initiated_at
    window = timedelta(minutes=settings.PENDING_WINDOW_MINUTES)
    cooldown = timedelta(seconds=settings.RETRY_COOLDOWN_SECONDS)

    checks = [
        GateCheck(code="G1_CLASS_PRE_DEBIT", passed=d.case_class in PRE_DEBIT, detail=str(d.case_class)),
        GateCheck(code="G2_NPCI_FINAL_FAILED", passed=n.available and n.status == "FAILED" and n.final,
                  detail=f"NPCI {n.status} final={n.final}"),
        GateCheck(code="G2_NO_DEBIT", passed=l.available and l.state == "NO_DEBIT" and l.debit_count == 0,
                  detail=f"ledger {l.state}"),
        GateCheck(code="G2_PENDING_WINDOW", passed=age >= window,
                  detail=f"{int(age.total_seconds() // 60)} min since payment, window {settings.PENDING_WINDOW_MINUTES} min"),
        GateCheck(code="G3_NO_CONFLICTS", passed=not b.conflicts and not b.suspicious,
                  detail=", ".join(c.code for c in b.conflicts + b.suspicious)),
        GateCheck(code="G4_PAYEE_FROM_RECORD",
                  passed=b.payee_source in TRUSTED_PAYEE_SOURCES and bool(VPA_RE.match(t.payee_vpa)) and bool(t.payee_name.strip()),
                  detail=f"payee from {b.payee_source}"),
        GateCheck(code="G5_COOLDOWN",
                  passed=history.last_attempt_at is None or now - history.last_attempt_at >= cooldown,
                  detail=f"last retry {history.last_attempt_at}"),
        GateCheck(code="G5_MAX_RETRIES", passed=history.accepted_count < settings.MAX_RETRIES_PER_TXN,
                  detail=f"{history.accepted_count}/{settings.MAX_RETRIES_PER_TXN} retries used"),
        GateCheck(code="G6_LIVE_RECHECK", passed=recheck_passed),
        GateCheck(code="G7_USER_CONFIRMED", passed=user_confirmed),
    ]
    return GateResult(checks=checks)
