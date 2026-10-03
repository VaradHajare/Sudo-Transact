"""Evidence assembler (spec 6.3): one bundle per payment from every source, plus conflict detection."""
import re
from datetime import datetime, timedelta

from app.config import Settings
from app.domain import (Claim, Conflict, EvidenceBundle, LedgerEvidence, MerchantEvidence, NpciEvidence,
                        TxnRecord)
from app.mock.sources import Sources

SUCCESS_LIKE = ("SUCCESS", "DEEMED")


def _source_conflicts(t: TxnRecord, n: NpciEvidence, l: LedgerEvidence, m: MerchantEvidence) -> list[Conflict]:
    out = []
    npci_success = n.available and n.status in SUCCESS_LIKE
    npci_final_failed = n.available and n.status == "FAILED" and n.final
    no_debit = l.available and l.state == "NO_DEBIT"
    credited = m.available and m.credited is True

    if npci_success and n.final and t.status == "FAILED":
        out.append(Conflict(code="RECORD_NPCI_MISMATCH", detail="Paytm record says FAILED, NPCI says SUCCESS"))
    if npci_final_failed and t.status == "SUCCESS":
        out.append(Conflict(code="RECORD_NPCI_MISMATCH", detail="Paytm record says SUCCESS, NPCI says FAILED"))
    if npci_success and no_debit:
        out.append(Conflict(code="NPCI_SUCCESS_NO_DEBIT", detail="NPCI says SUCCESS but the bank ledger shows no debit"))
    if credited and no_debit:
        out.append(Conflict(code="CREDIT_WITHOUT_DEBIT", detail="Merchant credited but the bank ledger shows no debit"))
    if npci_final_failed and credited:
        out.append(Conflict(code="NPCI_FAILED_BUT_CREDITED", detail="NPCI says FAILED but the merchant was credited"))
    if l.available and l.state == "REVERSED" and credited:
        out.append(Conflict(code="REVERSED_BUT_CREDITED", detail="Debit reversed but the merchant was also credited"))
    if l.available and l.state in ("DEBITED", "REVERSED") and l.amount_paise and l.amount_paise != t.amount_paise:
        out.append(Conflict(code="LEDGER_AMOUNT_MISMATCH",
                            detail=f"Ledger debit {l.amount_paise} paise != record {t.amount_paise} paise"))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _payee_matches(claimed: str, t: TxnRecord) -> bool:
    c = _norm(claimed)
    if not c:
        return True
    name, vpa = _norm(t.payee_name), _norm(t.payee_vpa.split("@")[0])
    # loose match: "sharma medical" ~ "Sharma Medicals"
    return c in name or name in c or c in vpa or name[: max(4, len(c) - 2)] == c[: max(4, len(c) - 2)]


def _suspicious(t: TxnRecord, l: LedgerEvidence, claims: list[Claim], recent_claim_count: int,
                settings: Settings) -> list[Conflict]:
    out = []
    for c in claims:
        if c.kind == "AMOUNT":
            try:
                claimed = int(c.value)
            except ValueError:
                continue
            allowed = {t.amount_paise, l.amount_paise * max(l.debit_count, 1) if l.amount_paise else t.amount_paise}
            if claimed not in allowed:
                out.append(Conflict(code="CLAIM_AMOUNT_MISMATCH",
                                    detail=f"User claims {claimed} paise, record says {t.amount_paise} paise"))
        elif c.kind == "PAYEE" and not _payee_matches(c.value, t):
            out.append(Conflict(code="CLAIM_PAYEE_MISMATCH",
                                detail=f"User names payee '{c.value}', record says '{t.payee_name}'"))
    if recent_claim_count >= settings.REPEAT_CLAIM_THRESHOLD:
        out.append(Conflict(code="REPEAT_CLAIMS",
                            detail=f"{recent_claim_count} claims in the last {settings.REPEAT_CLAIM_WINDOW_DAYS} days"))
    return out


def assemble(t: TxnRecord, n: NpciEvidence, l: LedgerEvidence, m: MerchantEvidence, *, now: datetime,
             settings: Settings, claims: list[Claim] | None = None, recent_claim_count: int = 0,
             payee_source: str = "PAYTM_RECORD") -> EvidenceBundle:
    """Pure: build the bundle and detect conflicts. Disagreements younger than the allowed lag are
    reported as `settling`, not as conflicts."""
    claims = claims or []
    raw = _source_conflicts(t, n, l, m)
    within_lag = now - t.initiated_at < timedelta(seconds=settings.EVIDENCE_LAG_SECONDS)
    return EvidenceBundle(
        txn=t, npci=n, ledger=l, merchant=m, payee_source=payee_source, claims=claims,
        recent_claim_count=recent_claim_count,
        conflicts=[] if within_lag else raw,
        settling=raw if within_lag else [],
        suspicious=_suspicious(t, l, claims, recent_claim_count, settings),
        assembled_at=now,
    )


def fetch_and_assemble(sources: Sources, txn_id: str, *, now: datetime, settings: Settings,
                       claims: list[Claim] | None = None, recent_claim_count: int = 0) -> EvidenceBundle:
    t = sources.payments.get_transaction(txn_id)
    if t is None:
        raise LookupError(f"unknown transaction {txn_id}")
    ev = sources.evidence
    return assemble(t, ev.npci_status(t.upi_ref), ev.bank_ledger(t.upi_ref), ev.merchant_credit(t.upi_ref),
                    now=now, settings=settings, claims=claims, recent_claim_count=recent_claim_count)
