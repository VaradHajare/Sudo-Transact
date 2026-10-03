"""Decision engine (spec 8.2). Deterministic; no LLM. Ordered rules, first match wins."""
import math
from datetime import datetime, time, timedelta

from app import clock
from app.config import Settings
from app.domain import Action, CaseClass as C, Decision, Diagnosis, EvidenceBundle, RetryHistory
from app.engine.retry_gate import PRE_DEBIT, SOFT_CONDITIONS, evaluate_gate


def compute_deadline(b: EvidenceBundle, settings: Settings) -> tuple[datetime, str]:
    """T+n turnaround: end of day (IST) n days after the debit date. Returns (naive UTC, sla kind)."""
    if b.npci.status in ("SUCCESS", "DEEMED"):
        kind, days = "merchant_confirmation_missing", settings.SLA_MERCHANT_CONFIRMATION_MISSING_DAYS
    else:
        kind, days = "beneficiary_credit_failure", settings.SLA_BENEFICIARY_CREDIT_FAILURE_DAYS
    debit_at = b.ledger.debited_at or b.txn.initiated_at
    day = clock.to_ist(debit_at).date() + timedelta(days=days)
    end_of_day = datetime.combine(day, time(23, 59, 59), tzinfo=clock.IST)
    return clock.ist_to_utc_naive(end_of_day), kind


def decide(d: Diagnosis, b: EvidenceBundle, now: datetime, settings: Settings, history: RetryHistory,
           *, recheck_changed: bool = False) -> Decision:
    trace = [f"class {d.case_class} ({d.source}, confidence {d.confidence:.2f})"]
    cls = d.case_class
    if d.confidence < settings.LLM_MIN_CONFIDENCE:
        trace.append(f"confidence below {settings.LLM_MIN_CONFIDENCE}: treated as AMBIGUOUS")
        cls = C.AMBIGUOUS
    recheck_at = now + timedelta(minutes=settings.RECHECK_INTERVAL_MINUTES)

    def dec(action: Action, rule: str, why: str, **kw) -> Decision:
        return Decision(action=action, rule=rule, trace=trace + [f"rule {rule}: {why}"], **kw)

    # 0. live re-check found a changed state
    if recheck_changed:
        return dec(Action.REASSEMBLE, "0", "live re-check found a changed state")
    # 1. conflicts or F9/F10
    if b.conflicts or b.suspicious or cls in (C.F9_CONFLICT, C.F10_SUSPICIOUS):
        codes = ", ".join(c.code for c in b.conflicts + b.suspicious) or str(cls)
        return dec(Action.ESCALATE, "1", f"conflicts or suspicious ({codes})")
    # 2. reversal confirmed
    if cls == C.F8_ALREADY_REVERSED:
        return dec(Action.CLOSE, "2", "reversal confirmed", notify=True)
    # 3. deemed success
    if cls == C.F5_DEEMED_SUCCESS:
        return dec(Action.CLOSE, "3", "payment succeeded; no retry, no dispute", notify=True)
    # 4. pending or bank downtime
    if cls in (C.F3_PENDING, C.F6_BANK_DOWNTIME):
        return dec(Action.WAIT, "4", "pending / bank downtime: schedule re-check", next_check_at=recheck_at)
    # 5. debited, not credited
    if cls == C.F4_DEBIT_NO_CREDIT:
        deadline, kind = compute_deadline(b, settings)
        trace.append(f"SLA {kind}: deadline {clock.iso_ist(deadline)}")
        if now < deadline:
            return dec(Action.WAIT, "5", "before deadline: wait for auto-reversal", notify=True,
                       deadline_ts=deadline, next_check_at=deadline)
        days_late = max(1, math.ceil((now - deadline).total_seconds() / 86400))
        return dec(Action.RAISE_DISPUTE, "5", f"deadline passed ({days_late} day(s) late): dispute + compensation",
                   notify=True, compensation=True, dispute_kind="DEBIT_NO_CREDIT",
                   deadline_ts=deadline, days_late=days_late)
    # 6. duplicate debit
    if cls == C.F7_DUPLICATE_DEBIT:
        return dec(Action.RAISE_DISPUTE, "6", "duplicate debit: dispute the extra debit", notify=True,
                   dispute_kind="DUPLICATE_DEBIT")
    # 7 / 7b. failed before debit
    if cls in PRE_DEBIT:
        gate = evaluate_gate(b, d, now, settings, history)
        failed = set(gate.failed)
        trace.append(f"retry gate failed on: {sorted(failed) or 'nothing'}")
        if not failed:
            return dec(Action.OFFER_RETRY, "7", "failed before debit and the retry gate passes")
        if failed <= SOFT_CONDITIONS:
            return dec(Action.WAIT, "7b", "gate fails only on finality / pending window / cooldown",
                       next_check_at=recheck_at)
    # 8. otherwise
    return dec(Action.ESCALATE, "8", "no safe automatic action")
