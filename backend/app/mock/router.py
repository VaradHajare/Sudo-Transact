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
from app.engine.pipeline import sweep_open_cases
from app.mock.sources import MockEvidenceSource, MockPaymentSource, MockUdir
from app.models import MockBankLedger, MockMerchantCredit, MockNpciStatus, MockUdirComplaint, Transaction

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
    # Until the step-6 scheduler owns this, a time-skip re-decides open cases right away.
    swept = sweep_open_cases(db, settings, trigger="CLOCK")
    db.commit()
    return {**_clock_view(db), "cases_rechecked": swept}


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
