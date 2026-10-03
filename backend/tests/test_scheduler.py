"""Background SLA / dispute scheduler: jobs table + one worker (spec 6.7)."""
import json
import time
from datetime import timedelta

import pytest

from app import clock
from app.bootstrap import init_database, prepare_cases
from app.engine import audit
from app.mock.router import InjectIn, LedgerPatch, apply_injection
from app.models import Case, CompensationClaim, Dispute, Job, Message, Transaction
from app.scheduler import Worker, _claim_next, recover_stale_jobs, run_due_jobs
from app.seed import seed_demo


@pytest.fixture
def world(db_session, settings):
    ids = seed_demo(db_session)
    prepare_cases(db_session, settings, ids)
    db_session.commit()
    return db_session


def case_of(db, txn_id) -> Case:
    return db.query(Case).filter(Case.txn_id == txn_id).one()


def queued(db, case_id):
    return db.query(Job).filter(Job.case_id == case_id, Job.status == "QUEUED").all()


def skip(db, **kw):
    clock.advance(db, int(timedelta(**kw).total_seconds()))
    db.commit()


def test_wait_decisions_schedule_jobs(world):
    s2 = case_of(world, "txn_s2_citymobiles")
    jobs = queued(world, s2.id)
    assert [j.kind for j in jobs] == ["SLA_DEADLINE"] and jobs[0].run_at == s2.deadline_ts
    assert [j.kind for j in queued(world, case_of(world, "txn_f3_gupta").id)] == ["RECHECK_CASE"]
    assert queued(world, case_of(world, "txn_s1_sharma").id) == []  # retry on offer: nothing to wait for


def test_nothing_runs_before_it_is_due(world, settings):
    assert run_due_jobs(world, settings) == []


def test_sla_deadline_job_raises_dispute_without_the_user(world, settings):
    s2 = case_of(world, "txn_s2_citymobiles")
    skip(world, days=2)
    done = run_due_jobs(world, settings)
    mine = [d for d in done if d["case_id"] == s2.id]
    assert mine and mine[0]["kind"] == "SLA_DEADLINE" and mine[0]["to"] == "DISPUTED"
    world.refresh(s2)
    assert world.query(Dispute).filter(Dispute.case_id == s2.id).count() == 1
    assert s2.has_unseen_update
    assert [j.kind for j in queued(world, s2.id)] == ["DISPUTE_FOLLOWUP"]
    events = [e.event_type for e in audit.events(world, s2.id)]
    assert events.index("RECHECK_PASSED") < events.index("DISPUTE_RAISED") < events.index("JOB_RUN")
    assert [e.actor for e in audit.events(world, s2.id) if e.event_type == "JOB_RUN"] == ["SCHEDULER"]


def test_followup_grows_compensation(world, settings):
    s2 = case_of(world, "txn_s2_citymobiles")
    skip(world, days=2)
    run_due_jobs(world, settings)
    comp = world.query(CompensationClaim).filter(CompensationClaim.case_id == s2.id).one()
    days0 = comp.days_late
    msgs0 = world.query(Message).filter(Message.case_id == s2.id).count()

    skip(world, days=1, minutes=1)
    done = run_due_jobs(world, settings)
    assert any(d["case_id"] == s2.id and d["kind"] == "DISPUTE_FOLLOWUP" for d in done)
    world.refresh(comp)
    assert comp.days_late == days0 + 1
    assert comp.amount_paise == comp.days_late * settings.compensation_per_day_paise
    assert world.query(Dispute).filter(Dispute.case_id == s2.id).count() == 1  # never a second dispute
    assert world.query(Message).filter(Message.case_id == s2.id).count() == msgs0  # no chat spam
    assert "COMPENSATION_UPDATED" in [e.event_type for e in audit.events(world, s2.id)]
    assert [j.kind for j in queued(world, s2.id)] == ["DISPUTE_FOLLOWUP"]  # keeps following up


def test_followup_catches_late_reversal_and_closes(world, settings):
    s2 = case_of(world, "txn_s2_citymobiles")
    skip(world, days=2)
    run_due_jobs(world, settings)
    txn = world.get(Transaction, "txn_s2_citymobiles")
    apply_injection(world, txn, InjectIn(txn_id=txn.id, ledger=LedgerPatch(state="REVERSED")), clock.now(world))
    world.commit()
    skip(world, days=1, minutes=1)
    run_due_jobs(world, settings)
    world.refresh(s2)
    assert (s2.class_, s2.state) == ("F8_ALREADY_REVERSED", "CLOSED")
    last = world.query(Message).filter(Message.case_id == s2.id).order_by(Message.id.desc()).first()
    assert last.kind == "update" and "came back" in last.text
    assert queued(world, s2.id) == []


def test_reversal_before_deadline_means_no_dispute(world, settings):
    s2 = case_of(world, "txn_s2_citymobiles")
    txn = world.get(Transaction, "txn_s2_citymobiles")
    apply_injection(world, txn, InjectIn(txn_id=txn.id, ledger=LedgerPatch(state="REVERSED")), clock.now(world))
    world.commit()
    skip(world, days=2)
    run_due_jobs(world, settings)
    world.refresh(s2)
    assert s2.state == "CLOSED" and world.query(Dispute).filter(Dispute.case_id == s2.id).count() == 0


def test_job_for_closed_case_is_skipped(world, settings):
    c10 = case_of(world, "txn_10_ramesh")  # CLOSED
    world.add(Job(kind="RECHECK_CASE", case_id=c10.id, run_at=clock.now(world), created_at=clock.now(world)))
    world.commit()
    done = run_due_jobs(world, settings)
    assert [d["status"] for d in done if d["case_id"] == c10.id] == ["SKIPPED"]


def test_failing_job_retries_then_fails(world, settings):
    now = clock.now(world)
    world.add(Job(kind="BOGUS", case_id=None, run_at=now, created_at=now))
    world.commit()
    statuses = []
    for _ in range(settings.JOB_MAX_ATTEMPTS):
        done = run_due_jobs(world, settings)
        statuses += [d["status"] for d in done if d["kind"] == "BOGUS"]
        skip(world, seconds=settings.JOB_RETRY_DELAY_SECONDS + 1)
    assert statuses == ["QUEUED"] * (settings.JOB_MAX_ATTEMPTS - 1) + ["FAILED"]
    job = world.query(Job).filter(Job.kind == "BOGUS").one()
    assert job.status == "FAILED" and "unknown job kind" in job.last_error


def test_claim_is_exclusive_and_stale_jobs_recover(world):
    skip(world, days=2)
    first = _claim_next(world)
    assert first is not None
    assert world.get(Job, first).status == "RUNNING"
    second = _claim_next(world)
    assert second != first
    assert recover_stale_jobs(world) >= 1
    world.expire_all()
    assert world.get(Job, first).status == "QUEUED"


def test_worker_thread_enforces_deadline_in_background(settings):
    s = settings.model_copy(update={"SEED_DEMO_DATA": True, "SCHEDULER_POLL_SECONDS": 0.05})
    engine, SessionLocal = init_database(s)
    with SessionLocal() as db:
        clock.advance(db, 2 * 86400)
        db.commit()
    worker = Worker(SessionLocal, s)
    worker.start()
    try:
        deadline = time.time() + 5
        state = None
        while time.time() < deadline:
            with SessionLocal() as db:
                state = db.query(Case).filter(Case.txn_id == "txn_s2_citymobiles").one().state
            if state == "DISPUTED":
                break
            time.sleep(0.05)
        assert state == "DISPUTED"
        with SessionLocal() as db:
            c = db.query(Case).filter(Case.txn_id == "txn_s2_citymobiles").one()
            runs = [json.loads(e.payload_json) for e in audit.events(db, c.id)
                    if e.event_type == "JOB_RUN" and e.actor == "SCHEDULER"]
            assert {"kind": "SLA_DEADLINE", "to": "DISPUTED"}.items() <= runs[0].items()
    finally:
        worker.stop()
        engine.dispose()


def test_clock_endpoint_runs_due_jobs(client):
    r = client.post("/mock/clock", json={"advance_days": 2}).json()
    s2 = [j for j in r["jobs_run"] if j.get("txn_id") == "txn_s2_citymobiles"]
    assert s2 and s2[0]["to"] == "DISPUTED"
    jobs = client.get("/mock/jobs?status=QUEUED").json()["jobs"]
    assert any(j["kind"] == "DISPUTE_FOLLOWUP" for j in jobs)
