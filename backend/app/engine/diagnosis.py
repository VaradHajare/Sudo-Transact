"""Diagnosis (spec 6.4): evidence bundle -> taxonomy class F1-F10, or AMBIGUOUS.

Rules only. AMBIGUOUS is where the LLM classifier plugs in later (build step 7); with the LLM off,
AMBIGUOUS goes to decision rule 8 (escalate).
"""
from app.config import Settings
from app.domain import CaseClass as C
from app.domain import Diagnosis, EvidenceBundle

BANK_DOWN_CODES = {"BANK_UNAVAILABLE", "ISSUER_DOWN", "BENEFICIARY_BANK_DOWN", "BANK_OFFLINE"}
TIMEOUT_CODES = {"TIMEOUT", "BAD_NETWORK", "NO_RESPONSE", "DEEMED_TIMEOUT"}


def diagnose(b: EvidenceBundle, settings: Settings) -> Diagnosis:
    n, l, m, t = b.npci, b.ledger, b.merchant, b.txn

    def out(cls: C, *reasons: str) -> Diagnosis:
        return Diagnosis(case_class=cls, confidence=1.0, source="RULES", reasons=list(reasons))

    if b.suspicious:
        return out(C.F10_SUSPICIOUS, *[s.code for s in b.suspicious])
    if b.conflicts:
        return out(C.F9_CONFLICT, *[c.code for c in b.conflicts])
    if b.settling:
        return out(C.F3_PENDING, "sources still settling inside the allowed lag", *[c.code for c in b.settling])
    if not (n.available and l.available):
        return Diagnosis(case_class=C.AMBIGUOUS, confidence=0.0,
                         reasons=["NPCI or bank ledger unavailable"])

    debited = l.state == "DEBITED"
    credited = m.available and m.credited is True
    code = n.reason_code or t.failure_code or ""

    if l.state == "REVERSED":
        return out(C.F8_ALREADY_REVERSED, "ledger shows the debit was reversed")
    if debited and l.debit_count >= 2 and (not m.available or m.credit_count <= 1):
        return out(C.F7_DUPLICATE_DEBIT, f"{l.debit_count} debits, {m.credit_count} credit")
    if n.status in ("SUCCESS", "DEEMED") and debited and credited:
        return out(C.F5_DEEMED_SUCCESS, f"NPCI {n.status}, debited and credited")
    if debited and not credited:
        return out(C.F4_DEBIT_NO_CREDIT, f"NPCI {n.status}, debited, merchant not credited")
    if l.state == "NO_DEBIT":
        if code in BANK_DOWN_CODES:
            return out(C.F6_BANK_DOWNTIME, f"bank unavailable ({code}), no debit")
        if n.status == "PENDING":
            return out(C.F3_PENDING, "NPCI PENDING, no debit yet")
        if n.status == "FAILED" and not n.final:
            return out(C.F2_TIMEOUT_PRE_DEBIT, "NPCI FAILED but not final, no debit")
        if n.status == "FAILED":
            if code in TIMEOUT_CODES:
                return out(C.F2_TIMEOUT_PRE_DEBIT, f"timed out ({code}), final FAILED, no debit")
            return out(C.F1_DECLINED_PRE_DEBIT, f"declined ({code or 'no code'}), final FAILED, no debit")
    return Diagnosis(case_class=C.AMBIGUOUS, confidence=0.0,
                     reasons=[f"no rule matched: record {t.status}, NPCI {n.status}, ledger {l.state}, credited {m.credited}"])
