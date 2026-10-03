"""Decision rules 0-8 and 7b (spec 8.2). First match wins. No LLM involved."""
from datetime import datetime, timedelta

from app.domain import Action, CaseClass, Diagnosis
from app.engine.decision import compute_deadline, decide
from app.engine.diagnosis import diagnose
from tests import factories as f

S = f.rules_settings()


def run(b, now=f.NOW, hist=None, recheck_changed=False, diag=None, settings=S):
    d = diag or diagnose(b, settings)
    return decide(d, b, now, settings, hist or f.history(), recheck_changed=recheck_changed)


# ---- rule 0
def test_rule0_recheck_changed_reassembles():
    dec = run(f.f1(), recheck_changed=True)
    assert (dec.action, dec.rule) == (Action.REASSEMBLE, "0")


def test_rule0_beats_everything_even_a_conflict():
    assert run(f.f9(), recheck_changed=True).rule == "0"


# ---- rule 1
def test_rule1_conflicts_escalate():
    dec = run(f.f9())
    assert (dec.action, dec.rule) == (Action.ESCALATE, "1")


def test_rule1_suspicious_escalates():
    dec = run(f.f10())
    assert (dec.action, dec.rule) == (Action.ESCALATE, "1")


def test_rule1_conflicts_escalate_even_if_class_looks_safe():
    b = f.f9()
    dec = run(b, diag=Diagnosis(case_class=CaseClass.F1_DECLINED_PRE_DEBIT))
    assert (dec.action, dec.rule) == (Action.ESCALATE, "1")


def test_rule1_class_f9_or_f10_escalates_without_conflict_list():
    for cls in (CaseClass.F9_CONFLICT, CaseClass.F10_SUSPICIOUS):
        dec = run(f.f1(), diag=Diagnosis(case_class=cls))
        assert (dec.action, dec.rule) == (Action.ESCALATE, "1")


# ---- rules 2, 3
def test_rule2_reversed_closes_and_notifies():
    dec = run(f.f8())
    assert (dec.action, dec.rule, dec.notify) == (Action.CLOSE, "2", True)


def test_rule3_deemed_success_closes_no_retry_no_dispute():
    dec = run(f.f5())
    assert (dec.action, dec.rule, dec.notify) == (Action.CLOSE, "3", True)
    assert dec.dispute_kind is None


# ---- rule 4
def test_rule4_pending_waits_with_recheck():
    dec = run(f.f3())
    assert (dec.action, dec.rule) == (Action.WAIT, "4")
    assert dec.next_check_at == f.NOW + timedelta(minutes=S.RECHECK_INTERVAL_MINUTES)


def test_rule4_bank_downtime_waits():
    dec = run(f.f6())
    assert (dec.action, dec.rule) == (Action.WAIT, "4")


# ---- rule 5
def test_rule5_before_deadline_waits_with_expected_by_date():
    b = f.f4()
    dec = run(b)
    assert (dec.action, dec.rule, dec.notify) == (Action.WAIT, "5", True)
    # debited 3 Oct IST, T+1 -> end of 4 Oct IST
    assert dec.deadline_ts == datetime(2026, 10, 4, 18, 29, 59)
    assert dec.next_check_at == dec.deadline_ts


def test_rule5_at_or_after_deadline_disputes_with_compensation():
    b = f.f4()
    deadline = compute_deadline(b, S)[0]
    dec = run(b, now=deadline + timedelta(days=1, minutes=1))
    assert (dec.action, dec.rule) == (Action.RAISE_DISPUTE, "5")
    assert dec.compensation and dec.notify and dec.dispute_kind == "DEBIT_NO_CREDIT"
    assert dec.days_late == 2


def test_rule5_exactly_at_deadline_disputes():
    b = f.f4()
    deadline = compute_deadline(b, S)[0]
    assert run(b, now=deadline).action == Action.RAISE_DISPUTE


def test_rule5_merchant_variant_uses_longer_sla():
    b = f.f4(npci_status="SUCCESS")
    b = f.bundle(t=b.txn.model_copy(update={"status": "SUCCESS"}), n=b.npci, l=b.ledger, m=b.merchant)
    deadline, kind = compute_deadline(b, S)
    assert kind == "merchant_confirmation_missing"
    assert deadline == datetime(2026, 10, 8, 18, 29, 59)  # T+5


def test_sla_days_come_from_config():
    b = f.f4()
    s2 = f.rules_settings(SLA_BENEFICIARY_CREDIT_FAILURE_DAYS=3)
    assert compute_deadline(b, s2)[0] == datetime(2026, 10, 6, 18, 29, 59)


# ---- rule 6
def test_rule6_duplicate_debit_disputes_duplicate():
    dec = run(f.f7())
    assert (dec.action, dec.rule, dec.dispute_kind, dec.notify) == (Action.RAISE_DISPUTE, "6", "DUPLICATE_DEBIT", True)
    assert not dec.compensation


# ---- rule 7
def test_rule7_f1_gate_passes_offers_retry():
    dec = run(f.f1())
    assert (dec.action, dec.rule) == (Action.OFFER_RETRY, "7")


def test_rule7_f2_gate_passes_offers_retry():
    dec = run(f.f2())
    assert (dec.action, dec.rule) == (Action.OFFER_RETRY, "7")


# ---- rule 7b (gate fails ONLY on finality / pending window / cooldown -> WAIT)
def test_rule7b_status_not_final_waits():
    b = f.bundle(t=f.txn(failure_code="TIMEOUT"), n=f.npci("FAILED", final=False, reason_code="TIMEOUT"))
    dec = run(b)
    assert (dec.action, dec.rule) == (Action.WAIT, "7b")


def test_rule7b_pending_window_not_elapsed_waits():
    b = f.bundle(t=f.txn(initiated_at=f.NOW - timedelta(minutes=5)))
    dec = run(b)
    assert (dec.action, dec.rule) == (Action.WAIT, "7b")


def test_rule7b_cooldown_not_passed_waits():
    dec = run(f.f1(), hist=f.history(accepted=0, last=f.NOW - timedelta(seconds=30)))
    assert (dec.action, dec.rule) == (Action.WAIT, "7b")


def test_rule7b_does_not_apply_when_a_hard_condition_also_fails():
    # not final AND payee not from the record -> not 7b -> rule 8
    b = f.bundle(n=f.npci("FAILED", final=False), payee_source="USER_SPEECH")
    dec = run(b)
    assert (dec.action, dec.rule) == (Action.ESCALATE, "8")


def test_rule7b_does_not_wait_forever_on_missing_npci_evidence():
    from app.domain import NpciEvidence
    b = f.bundle(n=NpciEvidence(available=False))
    dec = run(b, diag=Diagnosis(case_class=CaseClass.F1_DECLINED_PRE_DEBIT, confidence=0.95, source="LLM"))
    assert (dec.action, dec.rule) == (Action.ESCALATE, "8")


# ---- rule 8
def test_rule8_ambiguous_escalates():
    dec = run(f.f1(), diag=Diagnosis(case_class=CaseClass.AMBIGUOUS, confidence=0.0))
    assert (dec.action, dec.rule) == (Action.ESCALATE, "8")


def test_rule8_f1_with_max_retries_used_escalates():
    dec = run(f.f1(), hist=f.history(accepted=1, last=f.NOW - timedelta(hours=1)))
    assert (dec.action, dec.rule) == (Action.ESCALATE, "8")


def test_rule8_f1_payee_not_from_record_escalates():
    dec = run(f.bundle(payee_source="SMS"))
    assert (dec.action, dec.rule) == (Action.ESCALATE, "8")


def test_rule8_low_confidence_llm_class_escalates():
    d = Diagnosis(case_class=CaseClass.F3_PENDING, confidence=0.4, source="LLM")
    dec = run(f.f3(), diag=d)
    assert (dec.action, dec.rule) == (Action.ESCALATE, "8")


def test_trace_records_rule_and_class():
    dec = run(f.f1())
    assert any("rule 7" in line for line in dec.trace)
