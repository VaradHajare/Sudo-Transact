"""Evidence -> class (spec 8.1). Every class F1-F10 plus AMBIGUOUS."""
from datetime import timedelta

import pytest

from app.domain import CaseClass as C
from app.domain import Claim, NpciEvidence
from app.engine.diagnosis import diagnose
from tests import factories as f


@pytest.mark.parametrize("make,expected", [
    (f.f1, C.F1_DECLINED_PRE_DEBIT),
    (f.f2, C.F2_TIMEOUT_PRE_DEBIT),
    (f.f3, C.F3_PENDING),
    (f.f4, C.F4_DEBIT_NO_CREDIT),
    (f.f5, C.F5_DEEMED_SUCCESS),
    (f.f6, C.F6_BANK_DOWNTIME),
    (f.f7, C.F7_DUPLICATE_DEBIT),
    (f.f8, C.F8_ALREADY_REVERSED),
    (f.f9, C.F9_CONFLICT),
    (f.f10, C.F10_SUSPICIOUS),
])
def test_each_class(make, expected):
    assert diagnose(make(), f.rules_settings()).case_class == expected


def test_f2_when_npci_not_final_after_timeout():
    b = f.bundle(t=f.txn(failure_code="TIMEOUT"), n=f.npci("FAILED", final=False, reason_code="TIMEOUT"))
    assert diagnose(b, f.rules_settings()).case_class == C.F2_TIMEOUT_PRE_DEBIT


def test_f4_when_npci_success_but_merchant_not_credited():
    b = f.f4(npci_status="SUCCESS")
    b2 = f.bundle(t=b.txn.model_copy(update={"status": "SUCCESS"}), n=b.npci, l=b.ledger, m=b.merchant)
    assert diagnose(b2, f.rules_settings()).case_class == C.F4_DEBIT_NO_CREDIT


def test_missing_npci_is_ambiguous():
    b = f.bundle(n=NpciEvidence(available=False))
    assert diagnose(b, f.rules_settings()).case_class == C.AMBIGUOUS


def test_inconsistency_inside_lag_is_settling_not_conflict():
    t = f.txn(initiated_at=f.NOW - timedelta(seconds=30))
    b = f.bundle(t=t, n=f.npci("SUCCESS", reason_code=None), l=f.ledger("NO_DEBIT"), m=f.merchant(True))
    assert b.conflicts == [] and b.settling
    assert diagnose(b, f.rules_settings()).case_class == C.F3_PENDING


def test_conflict_codes():
    codes = {c.code for c in f.f9().conflicts}
    assert {"NPCI_SUCCESS_NO_DEBIT", "CREDIT_WITHOUT_DEBIT"} <= codes


def test_ledger_amount_mismatch_is_conflict():
    b = f.bundle(t=f.txn(debited=True), n=f.npci(reason_code="X"), l=f.ledger("DEBITED", amount_paise=99900))
    assert "LEDGER_AMOUNT_MISMATCH" in {c.code for c in b.conflicts}


def test_suspicious_signals():
    assert {c.code for c in f.f10().suspicious} == {"CLAIM_AMOUNT_MISMATCH"}
    b = f.bundle(claims=[Claim(kind="PAYEE", value="Raj Jewellers")])
    assert {c.code for c in b.suspicious} == {"CLAIM_PAYEE_MISMATCH"}
    b = f.bundle(recent_claim_count=3)
    assert {c.code for c in b.suspicious} == {"REPEAT_CLAIMS"}


def test_matching_claims_are_not_suspicious():
    b = f.bundle(claims=[Claim(kind="AMOUNT", value="35000"), Claim(kind="PAYEE", value="sharma medical")])
    assert b.suspicious == []
