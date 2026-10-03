"""Demo data. The backend owns it; web/data.js only formats it.

All times are relative to the moment the seed runs, so the problem payments are always
"today" / "yesterday" and inside their dispute timelines.

| txn id               | scenario | record                 | NPCI / ledger / merchant           | expected |
|----------------------|----------|------------------------|------------------------------------|----------|
| txn_s1_sharma        | S1       | FAILED, not debited    | FAILED final / NO_DEBIT / no credit | F1 -> OFFER_RETRY |
| txn_s2_citymobiles   | S2       | FAILED, debited        | FAILED final / DEBITED / no credit  | F4 -> WAIT, then dispute after deadline |
| txn_f3_gupta         | -        | PENDING                | PENDING / NO_DEBIT / no credit      | F3 -> WAIT |
| txn_s3_patel         | S3       | FAILED, not debited    | SUCCESS / NO_DEBIT / credited       | F9 -> ESCALATE |
| txn_10_ramesh        | spec 1.0 | FAILED, debited (10:37)| FAILED / REVERSED / no credit       | F8 -> CLOSE |
| txn_1ok_anil         | spec 1.0 | SUCCESS (11:18)        | SUCCESS / DEBITED / credited        | - |
| txn_1fail_anil       | spec 1.0 | FAILED "Bad Network" (11:19) | FAILED final / NO_DEBIT / no credit | F2 -> OFFER_RETRY |
"""
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app import clock
from app.models import MockBankLedger, MockMerchantCredit, MockNpciStatus, Transaction, User

DEMO_USER = ("u_demo", "Demo User", "en")


def _today_at_ist(now_utc: datetime, hh: int, mm: int) -> datetime:
    """Today at hh:mm IST (as naive UTC). If that time is still in the future, use yesterday."""
    now_ist = clock.to_ist(now_utc)
    at = datetime.combine(now_ist.date(), time(hh, mm), tzinfo=clock.IST)
    if at > now_ist - timedelta(minutes=5):
        at -= timedelta(days=1)
    return clock.ist_to_utc_naive(at)


def demo_transactions(now: datetime) -> list[dict]:
    m = timedelta(minutes=1)
    d = timedelta(days=1)
    t1037 = _today_at_ist(now, 10, 37)
    t1118 = t1037 + timedelta(minutes=41)
    t1119 = t1037 + timedelta(minutes=42)
    return [
        # ---- problem payments
        dict(id="txn_s1_sharma", upi_ref="627401118350", payee_name="Sharma Medicals",
             payee_vpa="sharmamedicals@paytm", amount_paise=35000, status="FAILED", debited=False,
             failure_code="BANK_DECLINED", failure_reason="Payment declined by your bank",
             category="Medical", note="Medicines", initiated_at=now - 40 * m,
             evidence=dict(npci=("FAILED", True, "BANK_DECLINED", "Declined by remitter bank"),
                           ledger=("NO_DEBIT", 0), merchant=False)),
        dict(id="txn_s2_citymobiles", upi_ref="627401221499", payee_name="City Mobiles",
             payee_vpa="citymobiles@okicici", amount_paise=149900, status="FAILED", debited=True,
             failure_code="BENEFICIARY_CREDIT_FAILED",
             failure_reason="Amount debited but not credited to the beneficiary",
             category="Electronics", note="Phone cover + charger", initiated_at=now - 120 * m,
             evidence=dict(npci=("FAILED", True, "BENEFICIARY_CREDIT_FAILED", "Credit to beneficiary failed"),
                           ledger=("DEBITED", 1), merchant=False)),
        dict(id="txn_f3_gupta", upi_ref="627400931220", payee_name="Gupta Stores",
             payee_vpa="guptastores@ybl", amount_paise=22000, status="PENDING", debited=False,
             failure_code=None, failure_reason=None, category="Groceries", note="Monthly ration",
             initiated_at=now - d - 30 * m,
             evidence=dict(npci=("PENDING", False, None, "Awaiting response from bank"),
                           ledger=("NO_DEBIT", 0), merchant=False)),
        dict(id="txn_s3_patel", upi_ref="627400842000", payee_name="Patel Electronics",
             payee_vpa="patelelectronics@okaxis", amount_paise=200000, status="FAILED", debited=False,
             failure_code="TXN_FAILED", failure_reason="Transaction failed",
             category="Electronics", note="Earphones", initiated_at=now - d - 180 * m,
             evidence=dict(npci=("SUCCESS", True, None, None),
                           ledger=("NO_DEBIT", 0), merchant=True)),
        # ---- the real test from spec 1.0
        dict(id="txn_10_ramesh", upi_ref="627401031037", payee_name="Ramesh Tea Stall",
             payee_vpa="rameshtea@paytm", amount_paise=1000, status="FAILED", debited=True,
             failure_code="BENEFICIARY_CREDIT_FAILED",
             failure_reason="Amount debited but not credited to the beneficiary",
             category="Food", note="Tea", initiated_at=t1037,
             evidence=dict(npci=("FAILED", True, "BENEFICIARY_CREDIT_FAILED", "Credit to beneficiary failed"),
                           ledger=("REVERSED", 1), merchant=False)),
        dict(id="txn_1ok_anil", upi_ref="627401031118", payee_name="Anil Kumar",
             payee_vpa="anilkumar@oksbi", amount_paise=100, status="SUCCESS", debited=True,
             failure_code=None, failure_reason=None, category="Transfer", note="Test",
             initiated_at=t1118,
             evidence=dict(npci=("SUCCESS", True, None, None), ledger=("DEBITED", 1), merchant=True)),
        dict(id="txn_1fail_anil", upi_ref="627401031119", payee_name="Anil Kumar",
             payee_vpa="anilkumar@oksbi", amount_paise=100, status="FAILED", debited=False,
             failure_code="BAD_NETWORK", failure_reason="Bad Network",
             category="Transfer", note="Test", initiated_at=t1119,
             evidence=dict(npci=("FAILED", True, "BAD_NETWORK", "Request timed out (bad network)"),
                           ledger=("NO_DEBIT", 0), merchant=False)),
        # ---- ordinary history
        dict(id="txn_swiggy", upi_ref="627400811389", payee_name="Swiggy", payee_vpa="swiggy@icici",
             amount_paise=38900, status="SUCCESS", debited=True, category="Food", note="Dinner",
             initiated_at=now - d - 300 * m,
             evidence=dict(npci=("SUCCESS", True, None, None), ledger=("DEBITED", 1), merchant=True)),
        dict(id="txn_kirana", upi_ref="627400721120", payee_name="Mahesh Kirana", payee_vpa="maheshkirana@ybl",
             amount_paise=12000, status="SUCCESS", debited=True, category="Groceries", note=None,
             initiated_at=now - 2 * d - 60 * m,
             evidence=dict(npci=("SUCCESS", True, None, None), ledger=("DEBITED", 1), merchant=True)),
        dict(id="txn_jio", upi_ref="627400631299", payee_name="Jio Prepaid Recharge", payee_vpa="jio@paytm",
             amount_paise=29900, status="SUCCESS", debited=True, category="Recharge", note="9876xxxx10",
             initiated_at=now - 3 * d - 200 * m,
             evidence=dict(npci=("SUCCESS", True, None, None), ledger=("DEBITED", 1), merchant=True)),
        dict(id="txn_rahul_in", upi_ref="627400541500", payee_name="Rahul Sharma", payee_vpa="rahul.s@okhdfc",
             amount_paise=50000, status="SUCCESS", debited=False, direction="IN", category="Transfer",
             note="Dinner split", initiated_at=now - 4 * d - 100 * m, evidence=None),
        dict(id="txn_msedcl", upi_ref="627400351240", payee_name="MSEDCL Electricity", payee_vpa="msedcl@sbi",
             amount_paise=124000, status="SUCCESS", debited=True, category="Bills", note="Sep bill",
             initiated_at=now - 6 * d - 400 * m,
             evidence=dict(npci=("SUCCESS", True, None, None), ledger=("DEBITED", 1), merchant=True)),
    ]


def add_transaction_with_evidence(db: Session, user_id: str, spec: dict) -> Transaction:
    spec = dict(spec)
    ev = spec.pop("evidence", None)
    initiated = spec["initiated_at"]
    txn = Transaction(
        payer_user_id=user_id, direction=spec.pop("direction", "OUT"),
        rail_label=spec.pop("rail_label", "UPI · State Bank of India ••4821"),
        updated_at=initiated + timedelta(seconds=30), **spec,
    )
    db.add(txn)
    if ev:
        n_status, n_final, n_code, n_reason = ev["npci"]
        db.add(MockNpciStatus(upi_ref=txn.upi_ref, status=n_status, final=n_final, reason_code=n_code,
                              reason=n_reason, updated_at=initiated + timedelta(seconds=20)))
        l_state, l_count = ev["ledger"]
        debited = l_state in ("DEBITED", "REVERSED")
        db.add(MockBankLedger(
            upi_ref=txn.upi_ref, state=l_state, debit_count=l_count,
            amount_paise=txn.amount_paise if debited else 0,
            debited_at=initiated + timedelta(seconds=5) if debited else None,
            reversed_at=initiated + timedelta(minutes=50) if l_state == "REVERSED" else None,
            updated_at=initiated + timedelta(seconds=5)))
        credited = bool(ev["merchant"])
        db.add(MockMerchantCredit(
            upi_ref=txn.upi_ref, credited=credited, credit_count=1 if credited else 0,
            credited_at=initiated + timedelta(seconds=8) if credited else None,
            updated_at=initiated + timedelta(seconds=8)))
    return txn


def seed_demo(db: Session) -> list[str]:
    """Insert the demo user and transactions. Returns the ids of failed/pending payments."""
    now = clock.now(db)
    uid, name, lang = DEMO_USER
    db.add(User(id=uid, name=name, language_pref=lang, created_at=now - timedelta(days=400)))
    db.flush()
    problem_ids = []
    for spec in demo_transactions(now):
        txn = add_transaction_with_evidence(db, uid, spec)
        if txn.direction == "OUT" and txn.status in ("FAILED", "PENDING"):
            problem_ids.append(txn.id)
    db.flush()
    return problem_ids
