import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from app import clock
from app.config import Settings
from app.models import CaseEvent, Transaction
from app.seed import seed_demo


def test_sqlite_only():
    with pytest.raises(ValueError):
        Settings(_env_file=None, DATABASE_URL="postgresql://x/y")


def test_wal_and_busy_timeout(db_session):
    assert db_session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    assert db_session.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_case_events_append_only(db_session):
    db_session.add(CaseEvent(case_id="c1", ts=clock.now(db_session), actor="SYSTEM", event_type="X"))
    db_session.commit()
    with pytest.raises(DatabaseError):
        db_session.execute(text("UPDATE case_events SET event_type='Y'"))
    db_session.rollback()
    with pytest.raises(DatabaseError):
        db_session.execute(text("DELETE FROM case_events"))
    db_session.rollback()


def test_clock_advance(db_session):
    before = clock.now(db_session)
    after = clock.advance(db_session, 2 * 86400)
    assert (after - before).total_seconds() >= 2 * 86400


def test_seed_has_demo_payments(db_session):
    problem = seed_demo(db_session)
    db_session.commit()
    assert {"txn_s1_sharma", "txn_s2_citymobiles", "txn_f3_gupta", "txn_s3_patel",
            "txn_10_ramesh", "txn_1fail_anil"} == set(problem)
    s2 = db_session.get(Transaction, "txn_s2_citymobiles")
    assert s2.status == "FAILED" and s2.debited and s2.amount_paise == 149900
    # spec 1.0: the Rs 1 failure is 42 minutes after the Rs 10 payment at 10:37
    t10 = db_session.get(Transaction, "txn_10_ramesh").initiated_at
    t1 = db_session.get(Transaction, "txn_1fail_anil").initiated_at
    assert clock.to_ist(t10).strftime("%H:%M") == "10:37"
    assert clock.to_ist(t1).strftime("%H:%M") == "11:19"
