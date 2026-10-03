"""Interfaces to the outside payment world, and their mock implementations.

The agent code only sees PaymentSource / EvidenceSource / DisputeChannel, so a sandbox or real
adapter can replace the mocks later without touching the engine. Mocks read the mock_* tables.
"""
import secrets
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.domain import LedgerEvidence, MerchantEvidence, NpciEvidence, TxnRecord
from app.models import MockBankLedger, MockMerchantCredit, MockNpciStatus, MockUdirComplaint, Transaction


class PaymentSource(Protocol):
    def get_transaction(self, txn_id: str) -> TxnRecord | None: ...
    def list_transactions(self, user_id: str) -> list[TxnRecord]: ...


class EvidenceSource(Protocol):
    def npci_status(self, upi_ref: str) -> NpciEvidence: ...
    def bank_ledger(self, upi_ref: str) -> LedgerEvidence: ...
    def merchant_credit(self, upi_ref: str) -> MerchantEvidence: ...


class DisputeChannel(Protocol):
    def raise_dispute(self, upi_ref: str, kind: str, amount_paise: int, at: datetime) -> str: ...


def to_record(t: Transaction) -> TxnRecord:
    return TxnRecord(
        id=t.id, upi_ref=t.upi_ref, user_id=t.payer_user_id, direction=t.direction,
        payee_vpa=t.payee_vpa, payee_name=t.payee_name, amount_paise=t.amount_paise,
        status=t.status, debited=t.debited, failure_code=t.failure_code,
        failure_reason=t.failure_reason, initiated_at=t.initiated_at,
    )


class MockPaymentSource:
    def __init__(self, db: Session):
        self.db = db

    def get_transaction(self, txn_id: str) -> TxnRecord | None:
        t = self.db.get(Transaction, txn_id)
        return to_record(t) if t else None

    def list_transactions(self, user_id: str) -> list[TxnRecord]:
        rows = (self.db.query(Transaction).filter(Transaction.payer_user_id == user_id)
                .order_by(Transaction.initiated_at.desc()).all())
        return [to_record(t) for t in rows]


class MockEvidenceSource:
    def __init__(self, db: Session):
        self.db = db

    def npci_status(self, upi_ref: str) -> NpciEvidence:
        r = self.db.get(MockNpciStatus, upi_ref)
        if r is None:
            return NpciEvidence(available=False)
        return NpciEvidence(status=r.status, final=r.final, reason_code=r.reason_code, reason=r.reason)

    def bank_ledger(self, upi_ref: str) -> LedgerEvidence:
        r = self.db.get(MockBankLedger, upi_ref)
        if r is None:
            return LedgerEvidence(available=False)
        return LedgerEvidence(state=r.state, debit_count=r.debit_count, amount_paise=r.amount_paise,
                              debited_at=r.debited_at, reversed_at=r.reversed_at)

    def merchant_credit(self, upi_ref: str) -> MerchantEvidence:
        r = self.db.get(MockMerchantCredit, upi_ref)
        if r is None:
            return MerchantEvidence(available=False)
        return MerchantEvidence(credited=r.credited, credit_count=r.credit_count, credited_at=r.credited_at)


class MockUdir:
    """Mock NPCI UDIR complaint channel."""

    def __init__(self, db: Session):
        self.db = db

    def raise_dispute(self, upi_ref: str, kind: str, amount_paise: int, at: datetime) -> str:
        ref = "UDIR" + secrets.token_hex(4).upper()
        self.db.add(MockUdirComplaint(ref=ref, upi_ref=upi_ref, kind=kind, amount_paise=amount_paise, raised_at=at))
        self.db.flush()
        return ref


class Sources:
    """Bundle of the three interfaces, so callers (and tests) can swap implementations together."""

    def __init__(self, payments: PaymentSource, evidence: EvidenceSource, disputes: DisputeChannel):
        self.payments = payments
        self.evidence = evidence
        self.disputes = disputes


def mock_sources(db: Session) -> Sources:
    return Sources(MockPaymentSource(db), MockEvidenceSource(db), MockUdir(db))
