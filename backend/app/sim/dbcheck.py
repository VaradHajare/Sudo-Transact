"""Checks that need the real database and API (run on a throwaway SQLite file, LLM off):

1. Pipeline agreement: a sample of simulated cases goes through `pipeline.process_transaction`
   (the code the app runs), with the world switching between the decision and the live re-check.
   Its action must equal the simulator loop's B1 action.
2. Time to a prepared answer: how long the user's tap on the mic takes for a case that was
   prepared in the background, against assembling it on demand.
3. Right payment attached: the spec 1.0 sequence over HTTP. A user chats about an older failed
   payment, a new payment fails, they tap the mic on it and ask about their "last payment". The
   session and the reply must be about the new payment.
"""
import statistics
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from app import clock, providers
from app.bootstrap import init_database
from app.config import Settings
from app.domain import LedgerEvidence, MerchantEvidence, NpciEvidence
from app.engine.pipeline import process_transaction
from app.mock.sources import MockPaymentSource, MockUdir, Sources
from app.models import Transaction, User
from app.sim.evaluate import run_case
from app.sim.generator import SimCase


class SwitchingEvidence:
    """Returns the decision-time world for the first assembly, then the action-time world, so the
    pipeline's live re-check sees the change exactly as it would in production."""

    def __init__(self, c: SimCase):
        self.c, self.calls = c, 0

    def _world(self):
        self.calls += 1
        return self.c.at_decision if self.calls <= 3 or self.c.at_action is None else self.c.at_action

    def npci_status(self, upi_ref: str) -> NpciEvidence:
        return self._world().npci

    def bank_ledger(self, upi_ref: str) -> LedgerEvidence:
        return self._world().ledger

    def merchant_credit(self, upi_ref: str) -> MerchantEvidence:
        return self._world().merchant


class _FrozenClock:
    def __init__(self):
        self.at = None
        self._real = clock.real_utcnow

    def __enter__(self):
        clock.real_utcnow = lambda: self.at
        return self

    def __exit__(self, *exc):
        clock.real_utcnow = self._real


def _add_txn(db, c: SimCase, user_id: str) -> Transaction:
    if db.get(User, user_id) is None:
        db.add(User(id=user_id, name="Sim user", language_pref="en", created_at=c.now - timedelta(days=100)))
        db.flush()
    t = c.txn
    row = Transaction(id=t.id, upi_ref=t.upi_ref, payer_user_id=user_id, direction="OUT", payee_vpa=t.payee_vpa,
                      payee_name=t.payee_name, amount_paise=t.amount_paise, status=t.status, debited=t.debited,
                      failure_code=t.failure_code, initiated_at=t.initiated_at, updated_at=t.initiated_at)
    db.add(row)
    db.flush()
    return row


def _pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 2)


def pipeline_agreement(cases: list[SimCase], settings: Settings) -> dict:
    # The DB pipeline counts repeat claims from stored disputes, not from the simulator's field, so
    # repeat-claimant cases are left out of this check.
    sample = [c for c in cases if c.recent_claim_count == 0]
    agree, mismatches, prep_ms, open_ms = 0, [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        s = settings.model_copy(update={"DATABASE_URL": f"sqlite:///{(Path(tmp) / 'sim.db').as_posix()}",
                                        "SEED_DEMO_DATA": False, "LLM_ENABLED": False, "SCHEDULER_ENABLED": False})
        engine, SessionLocal = init_database(s)
        saved = providers.current()
        providers.install(providers.Providers(settings=s))
        try:
            with SessionLocal() as db, _FrozenClock() as fc:
                for c in sample:
                    fc.at = c.now
                    _add_txn(db, c, f"su_{c.id}")
                    src = Sources(MockPaymentSource(db), SwitchingEvidence(c), MockUdir(db))
                    t0 = time.perf_counter()
                    out = process_transaction(db, s, c.id, "SIM_PREP", new_claims=c.claims or None, sources=src)
                    prep_ms.append((time.perf_counter() - t0) * 1000)  # = an on-demand open
                    if c.at_action is None:  # the user's tap on the case prepared above
                        t0 = time.perf_counter()
                        process_transaction(db, s, c.id, "USER_OPEN", sources=Sources(
                            MockPaymentSource(db), SwitchingEvidence(c), MockUdir(db)))
                        open_ms.append((time.perf_counter() - t0) * 1000)
                    expected = run_case(c, "B1", s).action
                    if out.case.decision == expected.value:
                        agree += 1
                    else:
                        mismatches.append({"case": c.id, "variant": c.variant, "pipeline": out.case.decision,
                                           "simulator": expected.value})
                db.commit()
        finally:
            providers.install(saved)
            engine.dispose()
    return {
        "sample": len(sample), "agree": agree, "agreement_rate": round(agree / len(sample), 4) if sample else None,
        "mismatches": mismatches[:20],
        "open_prepared_ms_median": _pct(open_ms, 0.5), "open_prepared_ms_p95": _pct(open_ms, 0.95),
        "open_on_demand_ms_median": _pct(prep_ms, 0.5), "open_on_demand_ms_p95": _pct(prep_ms, 0.95),
    }


def right_payment_attachment(settings: Settings, n_users: int = 50) -> dict:
    """Spec 1.0 sequence, over the real HTTP API."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.seed import add_transaction_with_evidence

    ok_session, ok_reply, first_turn_answer, latencies = 0, 0, 0, []
    with tempfile.TemporaryDirectory() as tmp:
        s = settings.model_copy(update={"DATABASE_URL": f"sqlite:///{(Path(tmp) / 'att.db').as_posix()}",
                                        "SEED_DEMO_DATA": False, "LLM_ENABLED": False, "STT_ENABLED": False,
                                        "TTS_ENABLED": False, "SCHEDULER_ENABLED": False})
        saved = providers.current()
        app = create_app(s)
        try:
            with TestClient(app) as client, app.state.SessionLocal() as db:
                now = clock.now(db)
                for u in range(n_users):
                    uid = f"att_{u}"
                    db.add(User(id=uid, name="User", language_pref="en", created_at=now - timedelta(days=50)))
                    db.flush()
                    old = add_transaction_with_evidence(db, uid, dict(
                        id=f"att_old_{u}", upi_ref=f"8{u:05d}1037", payee_name="Ramesh Tea Stall",
                        payee_vpa="rameshtea@paytm", amount_paise=1000, status="FAILED", debited=True,
                        failure_code="BENEFICIARY_CREDIT_FAILED", initiated_at=now - timedelta(minutes=45),
                        evidence=dict(npci=("FAILED", True, "BENEFICIARY_CREDIT_FAILED", None),
                                      ledger=("DEBITED", 1), merchant=False)))
                    db.commit()
                    tok = client.post("/v1/session", json={"user_id": uid}).json()["token"]
                    h = {"Authorization": f"Bearer {tok}"}
                    old_case = client.post("/v1/cases/open", json={"txn_id": old.id}, headers=h).json()["case"]
                    client.post("/v1/voice/turn", json={"case_id": old_case["id"], "text": "where is my 10 rupees"},
                                headers=h)
                    # a new payment fails a few minutes later
                    new = add_transaction_with_evidence(db, uid, dict(
                        id=f"att_new_{u}", upi_ref=f"8{u:05d}1119", payee_name="Anil Kumar",
                        payee_vpa="anilkumar@oksbi", amount_paise=100 * (u % 9 + 1), status="FAILED", debited=False,
                        failure_code="BAD_NETWORK", initiated_at=now - timedelta(minutes=2),
                        evidence=dict(npci=("FAILED", True, "BAD_NETWORK", None), ledger=("NO_DEBIT", 0),
                                      merchant=False)))
                    db.commit()
                    t0 = time.perf_counter()
                    opened = client.post("/v1/cases/open", json={"txn_id": new.id}, headers=h).json()
                    reply = client.post("/v1/voice/turn", json={"case_id": opened["case"]["id"],
                                                                 "text": "issue regarding last payment"},
                                        headers=h).json()
                    latencies.append((time.perf_counter() - t0) * 1000)
                    case = opened["case"]
                    if (case["txn_id"] == new.id and case["id"] != old_case["id"]
                            and not any("10 rupees" in (m.get("text") or "") for m in opened["messages"])):
                        ok_session += 1
                    facts = (reply.get("speak") or {}).get("facts") or {}
                    amount = str(new.amount_paise // 100)
                    if reply.get("case_id") == case["id"] and str(facts.get("amount", "")).replace("₹", "") == amount:
                        ok_reply += 1
                    if reply.get("decision") == case.get("decision") and reply.get("intent") != "off_topic":
                        first_turn_answer += 1
        finally:
            providers.install(saved)
            app.state.engine.dispose()
    return {
        "users": n_users,
        "session_bound_to_new_payment": ok_session,
        "reply_about_new_payment": ok_reply,
        "right_payment_rate": round(min(ok_session, ok_reply) / n_users, 4),
        "answered_in_first_turn": first_turn_answer,
        "open_plus_first_reply_ms_median": _pct(latencies, 0.5),
    }
