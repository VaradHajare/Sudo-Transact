"""The agent's core loop for one payment:

    assemble evidence -> diagnose -> decide -> live re-check (before any action) -> act -> notify

One case per payment (cases.txn_id is unique), so a new failure never lands in an old chat.
"""
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import clock, providers
from app.config import Settings
from app.conversation import llm_tasks
from app.domain import Action, CaseClass, Claim, Decision, Diagnosis, EvidenceBundle, RetryHistory
from app.engine import audit
from app.engine.actions import TERMINAL_STATES, apply_decision, escalate
from app.engine.decision import decide
from app.engine.diagnosis import diagnose
from app.engine.evidence import fetch_and_assemble
from app.engine.recheck import live_recheck
from app.engine.retry_gate import evaluate_gate
from app.mock.sources import Sources, mock_sources
from app.models import Case, Dispute, Job, Retry, Transaction, User

ACTIONS_NEEDING_RECHECK = {Action.OFFER_RETRY, Action.RAISE_DISPUTE, Action.CLOSE}
MAX_REASSEMBLE = 3
# Case creation that never sends a failed-payment report: the demo seed and the simulator.
QUIET_TRIGGERS = {"SEED", "SIM_PREP"}
# Not re-decided automatically: terminal, or paused while the user is on the retry pay screen.
NOT_REDECIDED = TERMINAL_STATES | {"RETRY_CONFIRMED"}


@dataclass
class Outcome:
    case: Case
    bundle: EvidenceBundle | None = None
    diagnosis: Diagnosis | None = None
    decision: Decision | None = None


def get_or_create_case(db: Session, txn: Transaction, now: datetime, trigger: str) -> Case:
    case = db.query(Case).filter(Case.txn_id == txn.id).one_or_none()
    if case:
        return case
    user = db.get(User, txn.payer_user_id)
    case = Case(id="c_" + secrets.token_hex(4), txn_id=txn.id, user_id=txn.payer_user_id, state="NEW",
                language=user.language_pref if user else "en", created_at=now, updated_at=now)
    db.add(case)
    db.flush()
    audit.log(db, case.id, now, "CASE_CREATED", {"txn_id": txn.id, "trigger": trigger})
    return case


def retry_history(db: Session, case_id: str) -> RetryHistory:
    accepted = (db.query(Retry).filter(Retry.case_id == case_id, Retry.accepted.is_(True))
                .order_by(Retry.confirmed_at.desc()).all())
    return RetryHistory(accepted_count=len(accepted), last_attempt_at=accepted[0].confirmed_at if accepted else None)


def recent_claim_count(db: Session, user_id: str, exclude_case: str, now: datetime, settings: Settings) -> int:
    """Disputes on the user's other cases in the window (repeat-claim signal)."""
    since = now - timedelta(days=settings.REPEAT_CLAIM_WINDOW_DAYS)
    return (db.query(Dispute).join(Case, Case.id == Dispute.case_id)
            .filter(Case.user_id == user_id, Case.id != exclude_case, Dispute.raised_at >= since).count())


def _load_claims(case: Case) -> list[Claim]:
    return [Claim(**c) for c in json.loads(case.claims_json or "[]")]


def _log_decision(db: Session, case: Case, now: datetime, b: EvidenceBundle, d: Diagnosis, dec: Decision) -> None:
    audit.log(db, case.id, now, "EVIDENCE_ASSEMBLED", {
        "npci": b.npci.model_dump(mode="json"), "ledger": b.ledger.model_dump(mode="json"),
        "merchant": b.merchant.model_dump(mode="json"),
        "conflicts": [c.code for c in b.conflicts], "suspicious": [c.code for c in b.suspicious],
        "settling": [c.code for c in b.settling], "fingerprint": b.fingerprint()})
    audit.log(db, case.id, now, "DIAGNOSED", d.model_dump(mode="json"))
    audit.log(db, case.id, now, "DECIDED", {"rule": dec.rule, "action": dec.action, "trace": dec.trace,
                                            "deadline": clock.iso_ist(dec.deadline_ts)})


def process_transaction(db: Session, settings: Settings, txn_id: str, trigger: str, *,
                        new_claims: list[Claim] | None = None, sources: Sources | None = None) -> Outcome:
    """Prepare or refresh the case for a payment. Safe to call repeatedly (idempotent actions)."""
    sources = sources or mock_sources(db)
    now = clock.now(db)
    txn = db.get(Transaction, txn_id)
    if txn is None:
        raise LookupError(f"unknown transaction {txn_id}")
    if txn.direction != "OUT":
        raise ValueError("only outgoing payments have cases")
    is_new = db.query(Case.id).filter(Case.txn_id == txn.id).first() is None
    case = get_or_create_case(db, txn, now, trigger)
    if is_new and settings.reports_on and trigger not in QUIET_TRIGGERS and txn.status in ("FAILED", "PENDING"):
        # Sent by the worker once this decision is committed (never slows the user's request).
        db.add(Job(kind="FAILURE_REPORT", case_id=case.id, run_at=now, created_at=now))

    if new_claims:
        merged = _load_claims(case) + new_claims
        case.claims_json = json.dumps([c.model_dump(mode="json") for c in merged])
        audit.log(db, case.id, now, "CLAIMS_RECORDED", {"claims": [c.model_dump(mode="json") for c in new_claims]},
                  actor="USER")
    if case.state in NOT_REDECIDED:
        return Outcome(case=case)

    hist = retry_history(db, case.id)
    rcc = recent_claim_count(db, case.user_id, case.id, now, settings)
    for attempt in range(MAX_REASSEMBLE):
        b = fetch_and_assemble(sources, txn_id, now=now, settings=settings, claims=_load_claims(case),
                               recent_claim_count=rcc)
        # Rule 0 across time: the world changed since this case was last decided.
        if attempt == 0 and case.evidence_fingerprint and b.fingerprint() != case.evidence_fingerprint:
            d0 = decide(diagnose(b, settings), b, now, settings, hist, recheck_changed=True)
            audit.log(db, case.id, now, "RECHECK_CHANGED", {"before_action": "re-decide", "trigger": trigger})
            audit.log(db, case.id, now, "DECIDED", {"rule": d0.rule, "action": d0.action, "trace": d0.trace})
        d = _diagnose(db, settings, case, b, now)
        dec = decide(d, b, now, settings, hist)
        _log_decision(db, case, now, b, d, dec)

        if dec.action in ACTIONS_NEEDING_RECHECK and not _already_done(db, case, dec):
            rc = live_recheck(db, sources, case.id, b, before=str(dec.action), now=now)
            if rc.changed:
                d0 = decide(d, b, now, settings, hist, recheck_changed=True)
                audit.log(db, case.id, now, "DECIDED", {"rule": d0.rule, "action": d0.action, "trace": d0.trace})
                continue
        apply_decision(db, sources, settings, case, b, d, dec, trigger, now)
        db.flush()
        return Outcome(case=case, bundle=b, diagnosis=d, decision=dec)

    escalate(db, case, "evidence kept changing during re-checks", now, b, d, dec)
    return Outcome(case=case, bundle=b, diagnosis=d, decision=dec)


def _diagnose(db: Session, settings: Settings, case: Case, b: EvidenceBundle, now: datetime) -> Diagnosis:
    """Rules first. Only an AMBIGUOUS result is handed to the LLM classifier (structured evidence
    only, JSON-validated); its confidence then goes through the decision engine's threshold."""
    d = diagnose(b, settings)
    p = providers.current()
    if d.case_class != CaseClass.AMBIGUOUS or not (p.llm and settings.LLM_ENABLED and settings.LLM_CLASSIFY_ENABLED):
        return d
    llm_d, info = llm_tasks.classify_ambiguous(p.llm, b)
    audit.log(db, case.id, now, "LLM_CLASSIFIED", {"rules_reasons": d.reasons, **info,
                                                   "result": llm_d.model_dump(mode="json") if llm_d else None},
              actor="AGENT")
    return llm_d or d


def _already_done(db: Session, case: Case, dec: Decision) -> bool:
    if dec.action == Action.RAISE_DISPUTE:
        return db.query(Dispute).filter(Dispute.case_id == case.id, Dispute.kind == dec.dispute_kind).count() > 0
    return False


def sweep_open_cases(db: Session, settings: Settings, trigger: str = "CLOCK") -> list[dict]:
    """Re-decide every open case (used after a time-skip until the step-6 scheduler exists)."""
    out = []
    for case in db.query(Case).filter(Case.state.notin_(NOT_REDECIDED)).all():
        before = case.state
        res = process_transaction(db, settings, case.txn_id, trigger)
        out.append({"case_id": case.id, "txn_id": case.txn_id, "from": before, "to": res.case.state,
                    "decision": res.case.decision, "rule": res.case.rule_id})
    return out


# ------------------------------------------------------------------ retry confirmation

@dataclass
class RetryConfirmResult:
    ok: bool
    case: Case
    payload: dict | None = None
    failed: list[str] | None = None
    recheck_changed: bool = False


def confirm_retry(db: Session, settings: Settings, case: Case, *, sources: Sources | None = None) -> RetryConfirmResult:
    """User said yes after the read-back. Re-check live, run the full gate (all 10 checks), then
    return the pay-screen payload. Payee and amount come only from the Paytm record."""
    sources = sources or mock_sources(db)
    now = clock.now(db)
    audit.log(db, case.id, now, "RETRY_CONFIRM_REQUESTED", {}, actor="USER")
    if case.state != "RETRY_OFFERED":
        return RetryConfirmResult(ok=False, case=case, failed=[f"case is {case.state}, no retry on offer"])

    b = fetch_and_assemble(sources, case.txn_id, now=now, settings=settings, claims=_load_claims(case),
                           recent_claim_count=recent_claim_count(db, case.user_id, case.id, now, settings))
    used = EvidenceBundle.model_validate({**b.model_dump(), **json.loads(case.evidence_json or "{}")})
    rc = live_recheck(db, sources, case.id, used, before="RETURN_PAY_SCREEN", now=now)
    if rc.changed:
        process_transaction(db, settings, case.txn_id, "RECHECK", sources=sources)  # rule 0
        return RetryConfirmResult(ok=False, case=case, failed=["G6_LIVE_RECHECK"], recheck_changed=True)

    d = diagnose(b, settings)
    gate = evaluate_gate(b, d, now, settings, retry_history(db, case.id), recheck_passed=True, user_confirmed=True)
    audit.log(db, case.id, now, "RETRY_GATE_EVALUATED",
              {"checks": [c.model_dump() for c in gate.checks], "passes": gate.fully_passes})
    if not gate.fully_passes or d.case_class not in (CaseClass.F1_DECLINED_PRE_DEBIT, CaseClass.F2_TIMEOUT_PRE_DEBIT):
        return RetryConfirmResult(ok=False, case=case, failed=gate.failed)

    retry = db.query(Retry).filter(Retry.case_id == case.id, Retry.accepted.is_(None)).first()
    if retry is None:
        retry = Retry(case_id=case.id, offered_at=now)
        db.add(retry)
    payload = {
        "case_id": case.id, "retry_of_txn_id": case.txn_id,
        "payee_vpa": b.txn.payee_vpa, "payee_name": b.txn.payee_name, "amount_paise": b.txn.amount_paise,
        "note": "Retry of failed payment", "payee_source": b.payee_source,
    }
    retry.accepted, retry.confirmed_at, retry.payload_json = True, now, json.dumps(payload)
    case.state = "RETRY_CONFIRMED"
    case.updated_at = now
    db.flush()
    payload["retry_id"] = retry.id
    audit.log(db, case.id, now, "RETRY_CONFIRMED", payload, actor="USER")
    return RetryConfirmResult(ok=True, case=case, payload=payload)
