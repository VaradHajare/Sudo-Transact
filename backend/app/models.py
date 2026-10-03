"""SQLAlchemy models (spec section 7, adapted to SQLite).

Conventions: money in integer paise; datetimes are naive UTC; JSON is stored as text
(`*_json` columns) so only portable column types are used.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# ---------------------------------------------------------------- core (Paytm side)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    language_pref: Mapped[str] = mapped_column(String, default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Transaction(Base):
    """Paytm's own transaction record. For direction IN, payee_* holds the sender."""
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    upi_ref: Mapped[str] = mapped_column(String, unique=True, index=True)
    payer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    direction: Mapped[str] = mapped_column(String, default="OUT")  # OUT | IN
    payee_vpa: Mapped[str] = mapped_column(String)
    payee_name: Mapped[str] = mapped_column(String)
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # SUCCESS | FAILED | PENDING
    debited: Mapped[bool] = mapped_column(Boolean, default=False)  # what the Paytm record believes
    failure_code: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    rail_label: Mapped[str | None] = mapped_column(String, nullable=True)
    retry_of_case_id: Mapped[str | None] = mapped_column(String, nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Case(Base):
    """One case (= one chat session) per payment. Never shared between payments."""
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    class_: Mapped[str | None] = mapped_column("class", String, nullable=True)
    state: Mapped[str] = mapped_column(String, default="NEW")
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String, nullable=True)
    deadline_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    language: Mapped[str] = mapped_column(String, default="en")
    has_unseen_update: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflicts_json: Mapped[str] = mapped_column(Text, default="[]")
    claims_json: Mapped[str] = mapped_column(Text, default="[]")
    case_file_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String)  # PAYTM_RECORD | NPCI | BANK_LEDGER | MERCHANT
    status: Mapped[str] = mapped_column(String)
    detail_json: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime)


class CaseEvent(Base):
    """APPEND-ONLY audit log (enforced by triggers in db.py)."""
    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String)  # SYSTEM | USER | AGENT | REVIEWER | SCHEDULER | MOCK
    event_type: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class Message(Base):
    """Chat history for a case (the case's session)."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    role: Mapped[str] = mapped_column(String)  # user | agent
    kind: Mapped[str] = mapped_column(String, default="reply")  # reply | update
    text: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String, default="en")
    intent: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    chips_json: Mapped[str] = mapped_column(Text, default="[]")
    actions_json: Mapped[str] = mapped_column(Text, default="[]")
    facts_json: Mapped[str] = mapped_column(Text, default="{}")
    audio_url: Mapped[str | None] = mapped_column(String, nullable=True)


class Retry(Base):
    __tablename__ = "retries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    offered_at: Mapped[datetime] = mapped_column(DateTime)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    new_txn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class Dispute(Base):
    __tablename__ = "disputes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String)  # DEBIT_NO_CREDIT | DUPLICATE_DEBIT
    mock_udir_ref: Mapped[str] = mapped_column(String)
    amount_paise: Mapped[int] = mapped_column(Integer)
    raised_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="RAISED")
    __table_args__ = (UniqueConstraint("case_id", "kind", name="uq_dispute_case_kind"),)


class CompensationClaim(Base):
    __tablename__ = "compensation_claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    days_late: Mapped[int] = mapped_column(Integer)
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="FLAGGED")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)  # APPROVE | REJECT | REQUEST_INFO
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime)


class Job(Base):
    """Background work (replaces Redis). Polled by one in-process worker (build step 6)."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)  # RECHECK_CASE | SLA_DEADLINE
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String, default="QUEUED")  # QUEUED | RUNNING | DONE | FAILED | CANCELLED
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String)
    key: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String)
    status_code: Mapped[int] = mapped_column(Integer)
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idem_user_key"),)


class SimRun(Base):
    __tablename__ = "sim_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_json: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime)


class SimCase(Base):
    __tablename__ = "sim_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("sim_runs.id"), index=True)
    ground_truth_class: Mapped[str] = mapped_column(String)
    txn_id: Mapped[str] = mapped_column(String)
    expected_action: Mapped[str] = mapped_column(String)


# ---------------------------------------------------------------- mock world (external systems)

class ClockState(Base):
    """Simulated clock: real UTC now + offset. Single row, id=1."""
    __tablename__ = "clock_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offset_seconds: Mapped[int] = mapped_column(Integer, default=0)


class MockNpciStatus(Base):
    __tablename__ = "mock_npci_status"
    upi_ref: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String)  # SUCCESS | FAILED | PENDING | DEEMED
    final: Mapped[bool] = mapped_column(Boolean, default=True)
    reason_code: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class MockBankLedger(Base):
    __tablename__ = "mock_bank_ledger"
    upi_ref: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str] = mapped_column(String)  # NO_DEBIT | DEBITED | REVERSED
    debit_count: Mapped[int] = mapped_column(Integer, default=0)
    amount_paise: Mapped[int] = mapped_column(Integer, default=0)  # per debit
    debited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class MockMerchantCredit(Base):
    __tablename__ = "mock_merchant_credit"
    upi_ref: Mapped[str] = mapped_column(String, primary_key=True)
    credited: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_count: Mapped[int] = mapped_column(Integer, default=0)
    credited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class MockUdirComplaint(Base):
    __tablename__ = "mock_udir_complaints"
    ref: Mapped[str] = mapped_column(String, primary_key=True)
    upi_ref: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    amount_paise: Mapped[int] = mapped_column(Integer)
    raised_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String, default="OPEN")
