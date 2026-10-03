"""Simulator and evaluation (spec 12-13). No network: B2 uses a fake classifier."""
from app.config import Settings
from app.domain import Action, CaseClass as C, Diagnosis
from app.sim import dbcheck
from app.sim.evaluate import metrics, record_only_world, run_baselines, run_case
from app.sim.generator import SimConfig, generate
from app.sim.report import render_markdown

S = Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:")
CASES = generate(SimConfig(n_cases=1500, seed=3))


def test_generator_is_deterministic_and_covers_every_class():
    again = generate(SimConfig(n_cases=1500, seed=3))
    assert [(c.id, c.variant, c.txn.amount_paise) for c in again] == [(c.id, c.variant, c.txn.amount_paise) for c in CASES]
    assert {c.truth for c in CASES} >= set(C) - {C.AMBIGUOUS}
    assert any(c.at_action is not None for c in CASES)
    assert any("source_outage" in c.variant for c in CASES)


def test_b1_targets_false_retry_and_false_action_zero():
    m = metrics([run_case(c, "B1", S) for c in CASES])
    assert m["false_retries"] == 0
    assert m["false_actions"] == 0
    assert m["recheck_cancelled"] > 0 and m["recheck_prevented_wrong_action"] == m["recheck_cancelled"]
    assert m["sla_breaches_caught"] == m["sla_breaches"] > 0


def test_b0_record_only_is_measurably_unsafe():
    m = metrics([run_case(c, "B0", S) for c in CASES])
    assert m["false_retries"] > 0  # the reason the extra evidence exists


def test_record_only_world_follows_the_record():
    c = next(c for c in CASES if c.variant == "f3_pending_record_says_failed")
    w = record_only_world(c)
    assert (w.npci.status, w.ledger.state) == ("FAILED", "NO_DEBIT")


def _overconfident_llm(b):
    """Worst-case classifier: always a confident class that would move money or close the case."""
    return Diagnosis(case_class=C.F7_DUPLICATE_DEBIT, confidence=0.99, source="LLM"), {}


def test_b2_even_a_reckless_llm_cannot_cause_false_actions():
    r = run_baselines(CASES, S, _overconfident_llm)
    assert r["B2"]["llm_classified"] > 0
    assert r["B2"]["false_retries"] == 0
    assert r["B2"]["false_actions"] == 0


def test_b2_skipped_without_llm_and_report_renders():
    r = run_baselines(CASES[:200], S, None)
    assert r["B2"] is None
    md = render_markdown({"generated_at": "x", "config": SimConfig(n_cases=200).to_json(), "seconds": 0,
                          "rules": {"LLM_MIN_CONFIDENCE": 0.7}, "llm": None, "variants": {"a": 1}, "baselines": r,
                          "pipeline_agreement": None, "right_payment": None})
    assert "simulator numbers" in md and "Not run" in md


def test_real_pipeline_agrees_with_the_simulator():
    changed = [c for c in CASES if c.at_action is not None][:20]
    sample = changed + [c for c in CASES[:80] if c not in changed]
    a = dbcheck.pipeline_agreement(sample, S)
    assert a["agree"] == a["sample"], a["mismatches"]


def test_right_payment_attached_over_http():
    a = dbcheck.right_payment_attachment(S, n_users=3)
    assert a["right_payment_rate"] == 1.0
