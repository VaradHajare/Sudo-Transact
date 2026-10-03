"""Pipeline on the seeded mock world: assemble -> diagnose -> decide -> re-check -> act -> notify."""
import json

import pytest

from app import clock
from app.bootstrap import prepare_cases
from app.domain import LedgerEvidence
from app.engine import audit
from app.engine.pipeline import confirm_retry, process_transaction, sweep_open_cases
from app.mock.router import InjectIn, LedgerPatch, apply_injection
from app.mock.sources import MockEvidenceSource, MockPaymentSource, MockUdir, Sources
from app.models import Case, CompensationClaim, Dispute, Message, Transaction
from app.seed import seed_demo


@pytest.fixture
def world(db_session, settings):
    ids = seed_demo(db_session)
    prepare_cases(db_session, settings, ids)
    db_session.commit()
    return db_session


def case_of(db, txn_id) -> Case:
    return db.query(Case).filter(Case.txn_id == txn_id).one()


def event_types(db, case):
    return [e.event_type for e in audit.events(db, case.id)]


def test_seeded_cases_are_prepared_before_the_user_asks(world):
    expected = {
        "txn_s1_sharma": ("F1_DECLINED_PRE_DEBIT", "OFFER_RETRY", "RETRY_OFFERED"),
        "txn_s2_citymobiles": ("F4_DEBIT_NO_CREDIT", "WAIT", "WAITING"),
        "txn_f3_gupta": ("F3_PENDING", "WAIT", "WAITING"),
        "txn_s3_patel": ("F9_CONFLICT", "ESCALATE", "ESCALATED"),
        "txn_10_ramesh": ("F8_ALREADY_REVERSED", "CLOSE", "CLOSED"),
        "txn_1fail_anil": ("F2_TIMEOUT_PRE_DEBIT", "OFFER_RETRY", "RETRY_OFFERED"),
    }
    for txn_id, (cls, decision, state) in expected.items():
        c = case_of(world, txn_id)
        assert (c.class_, c.decision, c.state) == (cls, decision, state), txn_id


def test_s2_has_deadline_and_sla_job(world):
    c = case_of(world, "txn_s2_citymobiles")
    assert c.rule_id == "5" and c.deadline_ts > clock.now(world)
    assert "RECHECK_PASSED" not in event_types(world, c)  # WAIT is not an action that needs a re-check


def test_actions_are_preceded_by_live_recheck(world):
    for txn_id in ("txn_s1_sharma", "txn_10_ramesh"):
        types = event_types(world, case_of(world, txn_id))
        assert types.index("RECHECK_PASSED") < max(i for i, t in enumerate(types) if t in ("RETRY_OFFERED", "NOTIFIED"))


def test_one_case_per_payment(world, settings):
    c10 = case_of(world, "txn_10_ramesh")
    c1 = case_of(world, "txn_1fail_anil")
    assert c10.id != c1.id
    again = process_transaction(world, settings, "txn_1fail_anil", "USER_OPEN").case
    assert again.id == c1.id
    assert world.query(Case).filter(Case.txn_id == "txn_1fail_anil").count() == 1


def test_background_reversal_notifies_in_that_case_only(world):
    c10 = case_of(world, "txn_10_ramesh")
    msgs = world.query(Message).filter(Message.case_id == c10.id).all()
    assert len(msgs) == 1 and msgs[0].kind == "update" and "came back" in msgs[0].text
    assert c10.has_unseen_update
    assert world.query(Message).filter(Message.case_id == case_of(world, "txn_1fail_anil").id).count() == 0


def test_s2_deadline_passes_dispute_and_compensation(world, settings):
    c = case_of(world, "txn_s2_citymobiles")
    clock.advance(world, 3 * 86400)
    sweep_open_cases(world, settings)
    world.commit()
    assert (c.state, c.decision, c.rule_id) == ("DISPUTED", "RAISE_DISPUTE", "5")
    d = world.query(Dispute).filter(Dispute.case_id == c.id).one()
    assert d.kind == "DEBIT_NO_CREDIT" and d.mock_udir_ref.startswith("UDIR") and d.amount_paise == 149900
    comp = world.query(CompensationClaim).filter(CompensationClaim.case_id == c.id).one()
    assert comp.days_late >= 1 and comp.amount_paise == comp.days_late * 100_00
    msg = world.query(Message).filter(Message.case_id == c.id).order_by(Message.id.desc()).first()
    assert msg.kind == "update" and d.mock_udir_ref in msg.text and c.has_unseen_update
    types = event_types(world, c)
    assert types.index("RECHECK_PASSED") < types.index("DISPUTE_RAISED") < types.index("COMPENSATION_FLAGGED")

    # idempotent: sweeping again raises nothing new
    sweep_open_cases(world, settings)
    assert world.query(Dispute).filter(Dispute.case_id == c.id).count() == 1
    assert world.query(Message).filter(Message.case_id == c.id).count() == 1


def test_s2_reversal_before_deadline_closes_instead(world, settings):
    txn = world.get(Transaction, "txn_s2_citymobiles")
    apply_injection(world, txn, InjectIn(txn_id=txn.id, ledger=LedgerPatch(state="REVERSED")), clock.now(world))
    clock.advance(world, 3 * 86400)
    sweep_open_cases(world, settings)
    c = case_of(world, "txn_s2_citymobiles")
    assert (c.class_, c.state) == ("F8_ALREADY_REVERSED", "CLOSED")
    assert world.query(Dispute).filter(Dispute.case_id == c.id).count() == 0
    assert "RECHECK_CHANGED" in event_types(world, c)  # rule 0: the world changed since the last decision


class LateDebitEvidence(MockEvidenceSource):
    """Ledger shows NO_DEBIT on the first read, then a late debit appears (state change mid-decision)."""

    def __init__(self, db):
        super().__init__(db)
        self.reads = 0

    def bank_ledger(self, upi_ref):
        self.reads += 1
        base = super().bank_ledger(upi_ref)
        if self.reads == 1:
            return base
        return LedgerEvidence(state="DEBITED", debit_count=1, amount_paise=35000,
                              debited_at=clock.real_utcnow())


def test_rule0_live_recheck_cancels_retry_offer(db_session, settings):
    seed_demo(db_session)
    sources = Sources(MockPaymentSource(db_session), LateDebitEvidence(db_session), MockUdir(db_session))
    out = process_transaction(db_session, settings, "txn_s1_sharma", "SEED", sources=sources)
    types = event_types(db_session, out.case)
    assert "RECHECK_CHANGED" in types
    decided = [json.loads(e.payload_json) for e in audit.events(db_session, out.case.id) if e.event_type == "DECIDED"]
    assert [d["rule"] for d in decided] == ["7", "0", "5"]  # offer -> cancelled by re-check -> re-decided as F4 wait
    assert out.case.state == "WAITING" and out.case.class_ == "F4_DEBIT_NO_CREDIT"
    assert "RETRY_OFFERED" not in types


def test_confirm_retry_returns_payload_from_record(world, settings):
    c = case_of(world, "txn_s1_sharma")
    res = confirm_retry(world, settings, c)
    assert res.ok, res.failed
    assert res.payload["payee_vpa"] == "sharmamedicals@paytm" and res.payload["amount_paise"] == 35000
    assert c.state == "RETRY_CONFIRMED"
    assert "RECHECK_PASSED" in event_types(world, c)
    # second confirmation is refused
    assert not confirm_retry(world, settings, c).ok
    # a paused case is not re-decided by the sweep (would otherwise hit max retries)
    sweep_open_cases(world, settings)
    assert c.state == "RETRY_CONFIRMED"


def test_confirm_retry_blocked_by_late_debit(world, settings):
    c = case_of(world, "txn_s1_sharma")
    txn = world.get(Transaction, "txn_s1_sharma")
    apply_injection(world, txn, InjectIn(txn_id=txn.id, ledger=LedgerPatch(state="DEBITED")), clock.now(world))
    res = confirm_retry(world, settings, c)
    assert not res.ok and res.recheck_changed
    assert c.state == "WAITING" and c.class_ == "F4_DEBIT_NO_CREDIT"


def test_confirm_retry_not_offered(world, settings):
    res = confirm_retry(world, settings, case_of(world, "txn_s2_citymobiles"))
    assert not res.ok


def test_s3_case_file(world):
    c = case_of(world, "txn_s3_patel")
    cf = json.loads(c.case_file_json)
    assert {x["code"] for x in cf["conflicts"]} >= {"NPCI_SUCCESS_NO_DEBIT", "CREDIT_WITHOUT_DEBIT"}
    assert cf["rule_trace"][-1].startswith("rule 1")
    assert cf["evidence"]["npci"]["status"] == "SUCCESS" and cf["recommended_actions"]
    assert "Patel Electronics" in cf["summary"]


def test_incoming_payment_has_no_case(world, settings):
    with pytest.raises(ValueError):
        process_transaction(world, settings, "txn_rahul_in", "USER_OPEN")
