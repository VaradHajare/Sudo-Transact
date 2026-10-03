"""Session, payment history, transaction events and the mock pay (PIN) call."""
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import clock
from app.api.v1.auth import current_user, issue_token
from app.api.v1.idempotency import run_idempotent
from app.api.v1.views import case_view, txn_view
from app.config import Settings
from app.conversation.turn import resolve_after_retry_payment
from app.deps import get_app_settings, get_db
from app.engine import audit
from app.engine.pipeline import process_transaction
from app.engine.retry_gate import VPA_RE
from app.mock.router import InjectIn, LedgerPatch, MerchantPatch, NpciPatch, apply_injection
from app.models import Case, Retry, Transaction, User

router = APIRouter()


# ------------------------------------------------------------------ session
class SessionIn(BaseModel):
    user_id: str | None = None


@router.post("/session")
def create_session(body: SessionIn, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)):
    if not settings.DEMO_MODE:
        raise HTTPException(404)
    user = db.get(User, body.user_id or settings.DEMO_USER_ID)
    if user is None:
        raise HTTPException(404, "unknown user")
    token, exp = issue_token(user.id, settings)
    return {"token": token, "expires_at": exp,
            "user": {"id": user.id, "name": user.name, "language": user.language_pref}}


# ------------------------------------------------------------------ history
@router.get("/transactions")
def list_transactions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (db.query(Transaction).filter(Transaction.payer_user_id == user.id)
            .order_by(Transaction.initiated_at.desc()).all())
    cases = {c.txn_id: c for c in db.query(Case).filter(Case.user_id == user.id).all()}
    return {"transactions": [txn_view(db, t, cases.get(t.id)) for t in rows]}


def _own_txn(db: Session, user: User, txn_id: str) -> Transaction:
    t = db.get(Transaction, txn_id)
    if t is None or t.payer_user_id != user.id:
        raise HTTPException(404, "transaction not found")
    return t


@router.get("/transactions/{txn_id}")
def get_transaction(txn_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return txn_view(db, _own_txn(db, user, txn_id))


# ------------------------------------------------------------------ ingest a (mock) Paytm transaction event
class MockEvidenceIn(BaseModel):
    npci: NpciPatch | None = None
    ledger: LedgerPatch | None = None
    merchant: MerchantPatch | None = None


class TxnEventIn(BaseModel):
    id: str | None = None
    upi_ref: str | None = None
    payee_vpa: str
    payee_name: str
    amount_paise: int = Field(gt=0)
    status: Literal["SUCCESS", "FAILED", "PENDING"]
    debited: bool = False
    failure_code: str | None = None
    failure_reason: str | None = None
    note: str | None = None
    category: str | None = None
    initiated_at: datetime | None = None
    mock_evidence: MockEvidenceIn | None = None


@router.post("/events/transactions", status_code=201)
def ingest_transaction(body: TxnEventIn, user: User = Depends(current_user), db: Session = Depends(get_db),
                       settings: Settings = Depends(get_app_settings),
                       idempotency_key: str | None = Header(default=None)):
    def run():
        now = clock.now(db)
        txn = Transaction(
            id=body.id or "txn_" + secrets.token_hex(5), upi_ref=body.upi_ref or str(6274_0000_0000 + secrets.randbelow(10**8)),
            payer_user_id=user.id, direction="OUT", payee_vpa=body.payee_vpa, payee_name=body.payee_name,
            amount_paise=body.amount_paise, status=body.status, debited=body.debited,
            failure_code=body.failure_code, failure_reason=body.failure_reason, note=body.note,
            category=body.category, rail_label="UPI · State Bank of India ••4821",
            initiated_at=body.initiated_at or now, updated_at=now)
        if db.get(Transaction, txn.id) or db.query(Transaction).filter(Transaction.upi_ref == txn.upi_ref).count():
            return 409, {"detail": "transaction already exists"}
        db.add(txn)
        db.flush()
        ev = body.mock_evidence or MockEvidenceIn()
        apply_injection(db, txn, InjectIn(txn_id=txn.id, npci=ev.npci, ledger=ev.ledger, merchant=ev.merchant), now)
        case = None
        if txn.status in ("FAILED", "PENDING"):  # detection: prepare the case in the background
            case = process_transaction(db, settings, txn.id, "EVENT").case
        return 201, {"transaction": txn_view(db, txn, case), "case": case_view(db, case) if case else None}

    return run_idempotent(db, user.id, idempotency_key, "/v1/events/transactions", body.model_dump(mode="json"), run)


# ------------------------------------------------------------------ mock pay screen (PIN)
class PaymentIn(BaseModel):
    payee_vpa: str
    payee_name: str
    amount_paise: int = Field(gt=0, le=10_000_000)
    pin: str
    note: str | None = None
    retry_of_case_id: str | None = None
    origin: Literal["retry", "scan"] | None = None  # "scan": a new payment from Scan & Pay


# Demo (DEMO_SCAN_PAY_FAILURE): how a Scan & Pay payment fails, as the Paytm record and the outside world see it.
SCAN_FAILURES = {
    "debited": dict(status="FAILED", debited=True, code="BENEFICIARY_CREDIT_FAILED",
                    reason="Amount debited but not credited to the merchant",
                    npci=NpciPatch(status="FAILED", reason_code="BENEFICIARY_CREDIT_FAILED",
                                   reason="Credit to beneficiary failed"),
                    ledger=LedgerPatch(state="DEBITED"), merchant=MerchantPatch(credited=False)),
    "declined": dict(status="FAILED", debited=False, code="BANK_DECLINED", reason="Payment declined by your bank",
                     npci=NpciPatch(status="FAILED", reason_code="BANK_DECLINED", reason="Declined by remitter bank"),
                     ledger=LedgerPatch(state="NO_DEBIT"), merchant=MerchantPatch(credited=False)),
    "bank_down": dict(status="FAILED", debited=False, code="BANK_UNAVAILABLE",
                      reason="Your bank is not responding right now",
                      npci=NpciPatch(status="FAILED", reason_code="BANK_UNAVAILABLE", reason="Remitter bank not available"),
                      ledger=LedgerPatch(state="NO_DEBIT"), merchant=MerchantPatch(credited=False)),
    "pending": dict(status="PENDING", debited=False, code=None, reason="Waiting for confirmation from your bank",
                    npci=NpciPatch(status="PENDING", final=False, reason="Awaiting response from bank"),
                    ledger=LedgerPatch(state="NO_DEBIT"), merchant=MerchantPatch(credited=False)),
}

# Merchants a demo QR scan "finds", in turn.
DEMO_QR_MERCHANTS = [
    ("Kaveri Restaurant", "kaverirest@paytm"), ("Om Sweets", "omsweets@okaxis"),
    ("Sai Hardware", "saihardware@ibl"), ("Priya Fashion", "priyafashion@okhdfc"),
]


@router.post("/scan")
def scan_qr(user: User = Depends(current_user), db: Session = Depends(get_db),
            settings: Settings = Depends(get_app_settings)):
    """Mock QR scan: returns the decoded merchant. Payee details from a QR are trusted (spec 8.4 G4)."""
    if not settings.DEMO_MODE:
        raise HTTPException(404, "scanning is mocked only in demo mode")
    n = db.query(Transaction).filter(Transaction.payer_user_id == user.id, Transaction.category == "Scan & Pay").count()
    name, vpa = DEMO_QR_MERCHANTS[n % len(DEMO_QR_MERCHANTS)]
    return {"payee_name": name, "payee_vpa": vpa}


@router.post("/payments", status_code=201)
def make_payment(body: PaymentIn, user: User = Depends(current_user), db: Session = Depends(get_db),
                 settings: Settings = Depends(get_app_settings), idempotency_key: str | None = Header(default=None)):
    """Mock payment from the in-app pay screen. A retry must match the confirmed retry payload exactly."""
    if not re.fullmatch(r"\d{4,6}", body.pin):
        raise HTTPException(422, "PIN must be 4-6 digits (mock)")
    if not VPA_RE.match(body.payee_vpa):
        raise HTTPException(422, "invalid payee VPA")
    req = body.model_dump(mode="json")
    req.pop("pin")  # never store the PIN, not even in the idempotency table

    def run():
        now = clock.now(db)
        case = None
        if body.retry_of_case_id:
            case = db.get(Case, body.retry_of_case_id)
            if case is None or case.user_id != user.id:
                return 404, {"detail": "case not found"}
            retry = (db.query(Retry).filter(Retry.case_id == case.id, Retry.accepted.is_(True),
                                            Retry.new_txn_id.is_(None)).order_by(Retry.id.desc()).first())
            payload = json.loads(retry.payload_json) if retry else None
            if case.state != "RETRY_CONFIRMED" or not payload or (
                    payload["payee_vpa"], payload["amount_paise"]) != (body.payee_vpa, body.amount_paise):
                return 409, {"detail": "no confirmed retry matches this payee and amount"}
        fail = (SCAN_FAILURES.get(settings.DEMO_SCAN_PAY_FAILURE)
                if settings.DEMO_MODE and body.origin == "scan" and not case else None)
        if fail:
            return 201, _failed_scan_payment(db, settings, user, body, fail, now)
        txn = Transaction(id="txn_" + secrets.token_hex(5), upi_ref=str(6274_0000_0000 + secrets.randbelow(10**8)),
                          payer_user_id=user.id, direction="OUT", payee_vpa=body.payee_vpa, payee_name=body.payee_name,
                          amount_paise=body.amount_paise, status="SUCCESS", debited=True, note=body.note,
                          category="Scan & Pay" if body.origin == "scan" else "Transfer",
                          rail_label="UPI · State Bank of India ••4821",
                          retry_of_case_id=case.id if case else None, initiated_at=now,
                          updated_at=now + timedelta(seconds=2))
        db.add(txn)
        db.flush()
        apply_injection(db, txn, InjectIn(txn_id=txn.id, npci=NpciPatch(status="SUCCESS"),
                                          ledger=LedgerPatch(state="DEBITED"), merchant=MerchantPatch(credited=True)), now)
        if case:
            resolve_after_retry_payment(db, case, txn)
            audit.log(db, case.id, now, "RETRY_PAYMENT_MADE", {"new_txn_id": txn.id}, actor="USER")
        return 201, {"transaction": txn_view(db, txn), "case": case_view(db, case) if case else None}

    return run_idempotent(db, user.id, idempotency_key, "/v1/payments", req, run)


def _failed_scan_payment(db: Session, settings: Settings, user: User, body: PaymentIn, fail: dict, now) -> dict:
    """Demo: the payment fails the configured way. Detection prepares the case at once, so the
    agent already knows the answer when it offers help."""
    txn = Transaction(id="txn_" + secrets.token_hex(5), upi_ref=str(6274_0000_0000 + secrets.randbelow(10**8)),
                      payer_user_id=user.id, direction="OUT", payee_vpa=body.payee_vpa, payee_name=body.payee_name,
                      amount_paise=body.amount_paise, status=fail["status"], debited=fail["debited"],
                      failure_code=fail["code"], failure_reason=fail["reason"], note=body.note, category="Scan & Pay",
                      rail_label="UPI · State Bank of India ••4821", initiated_at=now, updated_at=now)
    db.add(txn)
    db.flush()
    apply_injection(db, txn, InjectIn(txn_id=txn.id, npci=fail["npci"], ledger=fail["ledger"],
                                      merchant=fail["merchant"]), now)
    case = process_transaction(db, settings, txn.id, "EVENT").case
    return {"transaction": txn_view(db, txn, case), "case": case_view(db, case)}
