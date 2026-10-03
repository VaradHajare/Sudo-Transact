"""Builders for pure engine tests. Defaults describe a clean F1 case (declined, never debited)."""
from datetime import datetime, timedelta

from app.config import Settings
from app.domain import (Claim, LedgerEvidence, MerchantEvidence, NpciEvidence, RetryHistory,
                        TxnRecord)
from app.engine.evidence import assemble

NOW = datetime(2026, 10, 3, 9, 0, 0)  # naive UTC = 14:30 IST


def rules_settings(**kw) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="sqlite:///:memory:", **kw)


def txn(**kw) -> TxnRecord:
    base = dict(id="t1", upi_ref="111", user_id="u1", direction="OUT", payee_vpa="sharmamedicals@paytm",
                payee_name="Sharma Medicals", amount_paise=35000, status="FAILED", debited=False,
                failure_code="BANK_DECLINED", initiated_at=NOW - timedelta(minutes=40))
    base.update(kw)
    return TxnRecord(**base)


def npci(status="FAILED", final=True, reason_code="BANK_DECLINED", **kw) -> NpciEvidence:
    return NpciEvidence(status=status, final=final, reason_code=reason_code, **kw)


def ledger(state="NO_DEBIT", debit_count=None, amount_paise=None, **kw) -> LedgerEvidence:
    debited = state in ("DEBITED", "REVERSED")
    return LedgerEvidence(
        state=state,
        debit_count=debit_count if debit_count is not None else (1 if debited else 0),
        amount_paise=amount_paise if amount_paise is not None else (35000 if debited else 0),
        debited_at=(NOW - timedelta(minutes=40)) if debited else None,
        reversed_at=NOW - timedelta(minutes=5) if state == "REVERSED" else None, **kw)


def merchant(credited=False, credit_count=None) -> MerchantEvidence:
    return MerchantEvidence(credited=credited, credit_count=credit_count if credit_count is not None else int(credited))


def bundle(t=None, n=None, l=None, m=None, claims: list[Claim] | None = None, recent_claim_count=0,
           payee_source="PAYTM_RECORD", now=NOW, settings=None):
    return assemble(t or txn(), n or npci(), l or ledger(), m or merchant(), now=now,
                    settings=settings or rules_settings(), claims=claims or [],
                    recent_claim_count=recent_claim_count, payee_source=payee_source)


def history(accepted=0, last=None) -> RetryHistory:
    return RetryHistory(accepted_count=accepted, last_attempt_at=last)


# Evidence presets for each class -------------------------------------------------
def f1():
    return bundle()


def f2():
    return bundle(t=txn(failure_code="BAD_NETWORK"), n=npci(reason_code="BAD_NETWORK"))


def f3():
    return bundle(t=txn(status="PENDING", failure_code=None), n=npci("PENDING", final=False, reason_code=None))


def f4(minutes_ago=40, npci_status="FAILED", now=NOW):
    t = txn(debited=True, failure_code="BENEFICIARY_CREDIT_FAILED", initiated_at=now - timedelta(minutes=minutes_ago))
    l = ledger("DEBITED")
    l.debited_at = t.initiated_at
    return bundle(t=t, n=npci(npci_status, reason_code="BENEFICIARY_CREDIT_FAILED" if npci_status == "FAILED" else None),
                  l=l, now=now)


def f5():
    return bundle(t=txn(status="PENDING", failure_code=None), n=npci("DEEMED", reason_code=None),
                  l=ledger("DEBITED"), m=merchant(True))


def f6():
    return bundle(t=txn(failure_code="BANK_UNAVAILABLE"), n=npci(reason_code="BANK_UNAVAILABLE"))


def f7():
    return bundle(t=txn(status="SUCCESS", debited=True, failure_code=None), n=npci("SUCCESS", reason_code=None),
                  l=ledger("DEBITED", debit_count=2), m=merchant(True))


def f8():
    return bundle(t=txn(debited=True), n=npci(reason_code="BENEFICIARY_CREDIT_FAILED"), l=ledger("REVERSED"))


def f9():
    # NPCI says SUCCESS, merchant credited, but the bank shows no debit
    return bundle(n=npci("SUCCESS", reason_code=None), l=ledger("NO_DEBIT"), m=merchant(True))


def f10():
    return bundle(claims=[Claim(kind="AMOUNT", value="500000")])
