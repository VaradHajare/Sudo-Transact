"""/mock/* : the simulated outside world (Paytm records, NPCI, bank, merchant, UDIR, clock).

Internal / demo only. Not authenticated; only mounted when DEMO_MODE is on.
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app import clock
from app.config import Settings
from app.deps import get_app_settings, get_db
from app.mock.sources import MockEvidenceSource, MockPaymentSource, MockUdir
from app.models import Job, MockBankLedger, MockMerchantCredit, MockNpciStatus, MockUdirComplaint, Transaction
from app.scheduler import run_due_jobs

router = APIRouter(prefix="/mock", tags=["mock"])


@router.get("/paytm/transactions")
def paytm_transactions(user_id: str = "u_demo", db: Session = Depends(get_db)):
    return {"transactions": [r.model_dump(mode="json") for r in MockPaymentSource(db).list_transactions(user_id)]}


@router.get("/npci/status")
def npci_status(upi_ref: str, db: Session = Depends(get_db)):
    return {"upi_ref": upi_ref, **MockEvidenceSource(db).npci_status(upi_ref).model_dump(mode="json")}


@router.get("/bank/ledger")
def bank_ledger(upi_ref: str, db: Session = Depends(get_db)):
    return {"upi_ref": upi_ref, **MockEvidenceSource(db).bank_ledger(upi_ref).model_dump(mode="json")}


@router.get("/merchant/credit")
def merchant_credit(upi_ref: str, db: Session = Depends(get_db)):
    return {"upi_ref": upi_ref, **MockEvidenceSource(db).merchant_credit(upi_ref).model_dump(mode="json")}


class UdirIn(BaseModel):
    upi_ref: str
    kind: str
    amount_paise: int


@router.post("/npci/udir/dispute")
def udir_dispute(body: UdirIn, db: Session = Depends(get_db)):
    ref = MockUdir(db).raise_dispute(body.upi_ref, body.kind, body.amount_paise, clock.now(db))
    db.commit()
    return {"ref": ref, "status": "OPEN"}


@router.get("/npci/udir/disputes")
def udir_list(db: Session = Depends(get_db)):
    rows = db.query(MockUdirComplaint).order_by(MockUdirComplaint.raised_at.desc()).all()
    return {"disputes": [dict(ref=r.ref, upi_ref=r.upi_ref, kind=r.kind, amount_paise=r.amount_paise,
                              raised_at=clock.iso_ist(r.raised_at), status=r.status) for r in rows]}


# ------------------------------------------------------------------ clock (time-skip)

def _clock_view(db: Session) -> dict:
    n = clock.now(db)
    return {"now": clock.iso_ist(n), "offset_seconds": clock.get_offset(db)}


@router.get("/clock")
def get_clock(db: Session = Depends(get_db)):
    return _clock_view(db)


class ClockIn(BaseModel):
    advance_minutes: int = 0
    advance_hours: int = 0
    advance_days: int = 0
    reset: bool = False


@router.post("/clock")
def set_clock(body: ClockIn, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    if body.reset:
        clock.reset(db)
    seconds = body.advance_minutes * 60 + body.advance_hours * 3600 + body.advance_days * 86400
    if seconds < 0:
        raise HTTPException(400, "time only moves forward")
    clock.advance(db, seconds)
    db.commit()
    # Run the jobs that just became due (same code path as the background worker), so the demo
    # sees the result immediately instead of on the next poll.
    jobs_run = run_due_jobs(db, settings)
    return {**_clock_view(db), "jobs_run": jobs_run}


@router.get("/jobs")
def list_jobs(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    rows = q.order_by(Job.run_at).all()
    return {"now": clock.iso_ist(clock.now(db)),
            "jobs": [{"id": j.id, "kind": j.kind, "case_id": j.case_id, "run_at": clock.iso_ist(j.run_at),
                      "status": j.status, "attempts": j.attempts, "last_error": j.last_error} for j in rows]}


# ------------------------------------------------------------------ inject (change a payment's state)

class NpciPatch(BaseModel):
    status: Literal["SUCCESS", "FAILED", "PENDING", "DEEMED"]
    final: bool = True
    reason_code: str | None = None
    reason: str | None = None


class LedgerPatch(BaseModel):
    state: Literal["NO_DEBIT", "DEBITED", "REVERSED"]
    debit_count: int | None = None


class MerchantPatch(BaseModel):
    credited: bool
    credit_count: int | None = None


class InjectIn(BaseModel):
    txn_id: str | None = None
    upi_ref: str | None = None
    npci: NpciPatch | None = None
    ledger: LedgerPatch | None = None
    merchant: MerchantPatch | None = None

    @model_validator(mode="after")
    def _one_ref(self):
        if not (self.txn_id or self.upi_ref):
            raise ValueError("give txn_id or upi_ref")
        return self


@router.post("/inject")
def inject(body: InjectIn, db: Session = Depends(get_db)):
    if body.txn_id:
        txn = db.get(Transaction, body.txn_id)
    else:
        txn = db.query(Transaction).filter(Transaction.upi_ref == body.upi_ref).one_or_none()
    if txn is None:
        raise HTTPException(404, "unknown transaction")
    apply_injection(db, txn, body, clock.now(db))
    db.commit()
    ev = MockEvidenceSource(db)
    return {
        "txn_id": txn.id, "upi_ref": txn.upi_ref,
        "npci": ev.npci_status(txn.upi_ref).model_dump(mode="json"),
        "ledger": ev.bank_ledger(txn.upi_ref).model_dump(mode="json"),
        "merchant": ev.merchant_credit(txn.upi_ref).model_dump(mode="json"),
    }


def apply_injection(db: Session, txn: Transaction, body: InjectIn, at: datetime) -> None:
    ref = txn.upi_ref
    if body.npci:
        row = db.get(MockNpciStatus, ref) or MockNpciStatus(upi_ref=ref, updated_at=at)
        row.status, row.final = body.npci.status, body.npci.final
        row.reason_code, row.reason, row.updated_at = body.npci.reason_code, body.npci.reason, at
        db.add(row)
    if body.ledger:
        row = db.get(MockBankLedger, ref) or MockBankLedger(upi_ref=ref, state="NO_DEBIT", updated_at=at)
        row.state = body.ledger.state
        if body.ledger.state == "NO_DEBIT":
            row.debit_count, row.amount_paise, row.debited_at, row.reversed_at = 0, 0, None, None
        else:
            row.debit_count = body.ledger.debit_count or max(row.debit_count or 0, 1)
            row.amount_paise = txn.amount_paise
            row.debited_at = row.debited_at or at
            row.reversed_at = at if body.ledger.state == "REVERSED" else None
        row.updated_at = at
        db.add(row)
    if body.merchant:
        row = db.get(MockMerchantCredit, ref) or MockMerchantCredit(upi_ref=ref, updated_at=at)
        row.credited = body.merchant.credited
        row.credit_count = body.merchant.credit_count if body.merchant.credit_count is not None else int(body.merchant.credited)
        row.credited_at = at if body.merchant.credited else None
        row.updated_at = at
        db.add(row)
    db.flush()


# ------------------------------------------------------------------ demo scenarios (spec 17, optional parts)

OUTAGE_PAYEES = [("Kaveri Restaurant", "kaverirest@paytm", 64000), ("Om Sweets", "omsweets@okaxis", 45000),
                 ("Sai Hardware", "saihardware@ibl", 89900), ("Priya Fashion", "priyafashion@okhdfc", 129900)]


class ScenarioIn(BaseModel):
    name: Literal["bank_outage", "late_debit"]
    user_id: str = "u_demo"


@router.post("/scenario")
def scenario(body: ScenarioIn, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    """bank_outage: the payer's bank is down and a new payment fails (each call adds one). The case is
    prepared in the background, so a mic tap answers at once: F6, money safe, don't pay again.
    late_debit: a late debit lands on Sharma Medicals (S1) after the retry was offered. Saying "yes"
    then hits the live re-check, which cancels the retry and the agent says to wait."""
    import secrets
    from datetime import timedelta

    from app.engine.pipeline import process_transaction
    from app.seed import add_transaction_with_evidence

    now = clock.now(db)
    if body.name == "bank_outage":
        n = db.query(Transaction).filter(Transaction.id.like("txn_outage_%")).count()
        name, vpa, amount = OUTAGE_PAYEES[n % len(OUTAGE_PAYEES)]
        txn = add_transaction_with_evidence(db, body.user_id, dict(
            id=f"txn_outage_{secrets.token_hex(3)}", upi_ref=f"6274{secrets.randbelow(10**8):08d}",
            payee_name=name, payee_vpa=vpa, amount_paise=amount, status="FAILED", debited=False,
            failure_code="BANK_UNAVAILABLE", failure_reason="Your bank is not responding right now",
            category="Shopping", note=None, initiated_at=now - timedelta(seconds=30),
            evidence=dict(npci=("FAILED", True, "BANK_UNAVAILABLE", "Remitter bank not available"),
                          ledger=("NO_DEBIT", 0), merchant=False)))
        db.flush()
        out = process_transaction(db, settings, txn.id, "BACKGROUND")
        db.commit()
        return {"scenario": body.name, "txn_id": txn.id, "case_id": out.case.id, "class": out.case.class_,
                "decision": out.case.decision,
                "message": f"Bank outage: {name} payment failed and was prepared as {out.case.class_} -> {out.case.decision}. "
                           "Tap the mic on it in the phone."}
    txn = db.get(Transaction, "txn_s1_sharma")
    if txn is None:
        raise HTTPException(404, "Sharma Medicals demo payment missing: reset the demo data")
    apply_injection(db, txn, InjectIn(txn_id=txn.id, ledger=LedgerPatch(state="DEBITED")), now)
    db.commit()
    return {"scenario": body.name, "txn_id": txn.id,
            "message": "A late debit landed on Sharma Medicals. If the user now says yes to paying again, "
                       "the live re-check catches it and the agent says to wait instead."}
