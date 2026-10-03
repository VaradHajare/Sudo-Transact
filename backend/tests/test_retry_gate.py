"""Safe-retry gate (spec 8.4). All conditions must hold; each one alone blocks a retry."""
from datetime import timedelta

import pytest

from app.domain import CaseClass, Diagnosis
from app.engine.diagnosis import diagnose
from app.engine.retry_gate import SOFT_CONDITIONS, evaluate_gate
from tests import factories as f

S = f.rules_settings()


def gate(b, hist=None, recheck=True, confirmed=True, cls=None, now=f.NOW):
    d = Diagnosis(case_class=cls) if cls else diagnose(b, S)
    return evaluate_gate(b, d, now, S, hist or f.history(), recheck_passed=recheck, user_confirmed=confirmed)


def test_all_conditions_pass():
    g = gate(f.f1())
    assert g.fully_passes, g.failed


def test_condition_codes_cover_spec():
    codes = {c.code for c in gate(f.f1()).checks}
    assert codes == {"G1_CLASS_PRE_DEBIT", "G2_NPCI_FINAL_FAILED", "G2_NO_DEBIT", "G2_PENDING_WINDOW",
                     "G3_NO_CONFLICTS", "G4_PAYEE_FROM_RECORD", "G5_COOLDOWN", "G5_MAX_RETRIES",
                     "G6_LIVE_RECHECK", "G7_USER_CONFIRMED"}


def test_soft_conditions_are_the_7b_set():
    assert SOFT_CONDITIONS == {"G2_NPCI_FINAL_FAILED", "G2_PENDING_WINDOW", "G5_COOLDOWN"}


@pytest.mark.parametrize("cls", [c for c in CaseClass if c not in (CaseClass.F1_DECLINED_PRE_DEBIT, CaseClass.F2_TIMEOUT_PRE_DEBIT)])
def test_1_class_must_be_pre_debit(cls):
    assert gate(f.f1(), cls=cls).failed == ["G1_CLASS_PRE_DEBIT"]


def test_2a_npci_must_be_final_failed():
    assert gate(f.bundle(n=f.npci("FAILED", final=False))).failed == ["G2_NPCI_FINAL_FAILED"]


def test_2a_npci_pending_is_not_final_failed():
    b = f.bundle(n=f.npci("PENDING", final=False, reason_code=None))
    assert "G2_NPCI_FINAL_FAILED" in gate(b, cls=CaseClass.F2_TIMEOUT_PRE_DEBIT).failed


def test_2b_ledger_must_show_no_debit():
    b = f.bundle(l=f.ledger("DEBITED"))
    assert "G2_NO_DEBIT" in gate(b, cls=CaseClass.F1_DECLINED_PRE_DEBIT).failed


def test_2b_unavailable_ledger_is_not_proof_of_no_debit():
    from app.domain import LedgerEvidence
    b = f.bundle(l=LedgerEvidence(available=False))
    assert "G2_NO_DEBIT" in gate(b, cls=CaseClass.F1_DECLINED_PRE_DEBIT).failed


def test_2c_pending_window_must_have_elapsed():
    b = f.bundle(t=f.txn(initiated_at=f.NOW - timedelta(minutes=S.PENDING_WINDOW_MINUTES - 1)))
    assert gate(b).failed == ["G2_PENDING_WINDOW"]


def test_2c_pending_window_boundary_passes():
    b = f.bundle(t=f.txn(initiated_at=f.NOW - timedelta(minutes=S.PENDING_WINDOW_MINUTES)))
    assert gate(b).fully_passes


def test_3_no_conflicts():
    assert "G3_NO_CONFLICTS" in gate(f.f9(), cls=CaseClass.F1_DECLINED_PRE_DEBIT).failed


def test_3_no_suspicious_signals():
    assert gate(f.f10(), cls=CaseClass.F1_DECLINED_PRE_DEBIT).failed == ["G3_NO_CONFLICTS"]


@pytest.mark.parametrize("source", ["SMS", "USER_SPEECH", "LLM"])
def test_4_payee_must_come_from_record_or_qr(source):
    assert gate(f.bundle(payee_source=source)).failed == ["G4_PAYEE_FROM_RECORD"]


def test_4_qr_is_allowed():
    assert gate(f.bundle(payee_source="QR")).fully_passes


def test_4_invalid_vpa_fails():
    assert gate(f.bundle(t=f.txn(payee_vpa="not-a-vpa"))).failed == ["G4_PAYEE_FROM_RECORD"]


def test_5a_cooldown_must_pass():
    hist = f.history(accepted=0, last=f.NOW - timedelta(seconds=S.RETRY_COOLDOWN_SECONDS - 1))
    assert gate(f.f1(), hist=hist).failed == ["G5_COOLDOWN"]


def test_5a_cooldown_boundary_passes():
    hist = f.history(accepted=0, last=f.NOW - timedelta(seconds=S.RETRY_COOLDOWN_SECONDS))
    assert gate(f.f1(), hist=hist).fully_passes


def test_5b_max_retries_per_txn():
    hist = f.history(accepted=S.MAX_RETRIES_PER_TXN, last=f.NOW - timedelta(hours=2))
    assert gate(f.f1(), hist=hist).failed == ["G5_MAX_RETRIES"]


def test_6_live_recheck_must_pass():
    assert gate(f.f1(), recheck=False).failed == ["G6_LIVE_RECHECK"]


def test_7_user_must_confirm():
    assert gate(f.f1(), confirmed=False).failed == ["G7_USER_CONFIRMED"]


def test_offer_phase_leaves_6_and_7_unevaluated():
    g = gate(f.f1(), recheck=None, confirmed=None)
    assert g.passes and not g.fully_passes
