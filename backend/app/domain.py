"""Domain types shared by the sources, the engine and the API. Pure data, no DB access."""
import hashlib
import json
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CaseClass(StrEnum):
    F1_DECLINED_PRE_DEBIT = "F1_DECLINED_PRE_DEBIT"
    F2_TIMEOUT_PRE_DEBIT = "F2_TIMEOUT_PRE_DEBIT"
    F3_PENDING = "F3_PENDING"
    F4_DEBIT_NO_CREDIT = "F4_DEBIT_NO_CREDIT"
    F5_DEEMED_SUCCESS = "F5_DEEMED_SUCCESS"
    F6_BANK_DOWNTIME = "F6_BANK_DOWNTIME"
    F7_DUPLICATE_DEBIT = "F7_DUPLICATE_DEBIT"
    F8_ALREADY_REVERSED = "F8_ALREADY_REVERSED"
    F9_CONFLICT = "F9_CONFLICT"
    F10_SUSPICIOUS = "F10_SUSPICIOUS"
    AMBIGUOUS = "AMBIGUOUS"


class Action(StrEnum):
    REASSEMBLE = "REASSEMBLE"  # rule 0
    ESCALATE = "ESCALATE"
    CLOSE = "CLOSE"
    WAIT = "WAIT"
    RAISE_DISPUTE = "RAISE_DISPUTE"
    OFFER_RETRY = "OFFER_RETRY"


# --------------------------------------------------------------- evidence from each source

class TxnRecord(BaseModel):
    """Paytm's own transaction record (PaymentSource)."""
    id: str
    upi_ref: str
    user_id: str
    direction: str
    payee_vpa: str
    payee_name: str
    amount_paise: int
    status: str  # SUCCESS | FAILED | PENDING
    debited: bool
    failure_code: str | None = None
    failure_reason: str | None = None
    initiated_at: datetime


class NpciEvidence(BaseModel):
    available: bool = True
    status: str | None = None  # SUCCESS | FAILED | PENDING | DEEMED
    final: bool = False
    reason_code: str | None = None
    reason: str | None = None


class LedgerEvidence(BaseModel):
    available: bool = True
    state: str | None = None  # NO_DEBIT | DEBITED | REVERSED
    debit_count: int = 0
    amount_paise: int = 0
    debited_at: datetime | None = None
    reversed_at: datetime | None = None


class MerchantEvidence(BaseModel):
    available: bool = True
    credited: bool | None = None
    credit_count: int = 0
    credited_at: datetime | None = None


class Claim(BaseModel):
    """Something the user asserted (from a voice turn). Untrusted: only compared with evidence."""
    kind: str  # AMOUNT | PAYEE | DEBITED
    value: str
    ts: datetime | None = None


class Conflict(BaseModel):
    code: str
    detail: str


class EvidenceBundle(BaseModel):
    txn: TxnRecord
    npci: NpciEvidence
    ledger: LedgerEvidence
    merchant: MerchantEvidence
    payee_source: str = "PAYTM_RECORD"  # PAYTM_RECORD | QR | other (never SMS / user speech)
    claims: list[Claim] = Field(default_factory=list)
    recent_claim_count: int = 0  # user's claims across cases in the repeat-claim window
    conflicts: list[Conflict] = Field(default_factory=list)  # sources disagree (-> F9)
    suspicious: list[Conflict] = Field(default_factory=list)  # claim vs evidence, repeat claims (-> F10)
    settling: list[Conflict] = Field(default_factory=list)  # disagreements still inside the allowed lag
    assembled_at: datetime

    def fingerprint(self) -> str:
        """Hash of the external state the decision relies on; the live re-check compares it."""
        state = {
            "npci": self.npci.model_dump(mode="json"),
            "ledger": self.ledger.model_dump(mode="json"),
            "merchant": self.merchant.model_dump(mode="json"),
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------- engine outputs

class Diagnosis(BaseModel):
    case_class: CaseClass
    confidence: float = 1.0
    source: str = "RULES"  # RULES | LLM
    reasons: list[str] = Field(default_factory=list)


class GateCheck(BaseModel):
    code: str
    passed: bool | None  # None = not evaluated yet (needs a later phase)
    detail: str = ""


class GateResult(BaseModel):
    checks: list[GateCheck]

    @property
    def failed(self) -> list[str]:
        return [c.code for c in self.checks if c.passed is False]

    @property
    def passes(self) -> bool:
        """All evaluated conditions passed (unevaluated ones are ignored)."""
        return not self.failed

    @property
    def fully_passes(self) -> bool:
        return all(c.passed is True for c in self.checks)


class RetryHistory(BaseModel):
    accepted_count: int = 0
    last_attempt_at: datetime | None = None


class Decision(BaseModel):
    action: Action
    rule: str  # "0".."8", "7b"
    notify: bool = False
    compensation: bool = False
    dispute_kind: str | None = None
    deadline_ts: datetime | None = None
    days_late: int = 0
    next_check_at: datetime | None = None
    trace: list[str] = Field(default_factory=list)
