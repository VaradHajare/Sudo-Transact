"""Labelled case generator (spec 12.2).

Each case is a Paytm record plus the external world (NPCI, bank ledger, merchant) at decision time,
and optionally a different world at action time (to exercise the live re-check). The generator
knows what it built, so it labels every case with a ground-truth class and the set of acceptable
actions. Those labels come from the scenario, never from the engine, so the engine is graded
against an independent answer key.

The class mix and noise rates are ASSUMPTIONS for testing, not real-world statistics.
"""
import random
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from app import clock
from app.domain import Action, CaseClass as C, Claim, LedgerEvidence, MerchantEvidence, NpciEvidence, TxnRecord

DEFAULT_MIX = {
    C.F1_DECLINED_PRE_DEBIT: 0.14, C.F2_TIMEOUT_PRE_DEBIT: 0.12, C.F3_PENDING: 0.10,
    C.F4_DEBIT_NO_CREDIT: 0.16, C.F5_DEEMED_SUCCESS: 0.08, C.F6_BANK_DOWNTIME: 0.10,
    C.F7_DUPLICATE_DEBIT: 0.06, C.F8_ALREADY_REVERSED: 0.08, C.F9_CONFLICT: 0.08, C.F10_SUSPICIOUS: 0.08,
}


@dataclass
class SimConfig:
    n_cases: int = 3000
    seed: int = 7
    mix: dict = field(default_factory=lambda: dict(DEFAULT_MIX))
    p_record_stale: float = 0.30  # Paytm record lags the real state (status / debited flag out of date)
    p_state_change: float = 0.10  # world changes between decision and action (where the class allows it)
    p_source_outage: float = 0.06  # NPCI or bank ledger unreachable when the case is assembled
    p_settling: float = 0.03  # sources disagree but still inside the allowed lag

    def to_json(self) -> dict:
        return {**{k: v for k, v in self.__dict__.items() if k != "mix"},
                "mix": {str(k): v for k, v in self.mix.items()}}


@dataclass
class World:
    npci: NpciEvidence
    ledger: LedgerEvidence
    merchant: MerchantEvidence


@dataclass
class SimCase:
    id: str
    variant: str
    truth: C  # class of the payment as it really is when the action happens
    acceptable: set[Action]
    txn: TxnRecord
    now: datetime
    at_decision: World
    at_action: World | None = None  # None: nothing changes before the action
    claims: list[Claim] = field(default_factory=list)
    recent_claim_count: int = 0
    retry_unsafe: bool = True  # money debited, pending or unknown: a retry could pay twice
    outage: bool = False  # a bank-outage case (for "answered without a human")
    sla_breach: bool = False  # F4 past its deadline: a dispute + compensation is owed

    @property
    def expected_action(self) -> str:
        return "|".join(sorted(a.value for a in self.acceptable))


PAYEES = [
    ("Sharma Medicals", "sharmamedicals@paytm"), ("City Mobiles", "citymobiles@okicici"),
    ("Gupta Stores", "guptastores@ybl"), ("Ramesh Tea Stall", "rameshtea@paytm"),
    ("Anil Kumar", "anilkumar@oksbi"), ("Mahesh Kirana", "maheshkirana@ybl"),
    ("Jio Prepaid Recharge", "jio@paytm"), ("MSEDCL Electricity", "msedcl@sbi"),
    ("Priya Fashion", "priyafashion@okhdfc"), ("Sai Hardware", "saihardware@ibl"),
    ("Kaveri Restaurant", "kaverirest@paytm"), ("Om Sweets", "omsweets@okaxis"),
]
DECLINE_CODES = ["BANK_DECLINED", "INSUFFICIENT_FUNDS", "LIMIT_EXCEEDED", "WRONG_PIN"]
TIMEOUT_CODES = ["TIMEOUT", "BAD_NETWORK", "NO_RESPONSE"]
BANK_DOWN_CODES = ["BANK_UNAVAILABLE", "ISSUER_DOWN", "BENEFICIARY_BANK_DOWN"]


def sla_deadline(debited_at: datetime, days: int) -> datetime:
    """T+n turnaround, end of day IST (calendar fact from the RBI table, mirrored here on purpose)."""
    day = clock.to_ist(debited_at).date() + timedelta(days=days)
    return clock.ist_to_utc_naive(datetime.combine(day, time(23, 59, 59), tzinfo=clock.IST))


class _Gen:
    def __init__(self, cfg: SimConfig, base_now: datetime):
        self.cfg, self.r, self.base_now = cfg, random.Random(cfg.seed), base_now

    # ---------------------------------------------------------------- building blocks
    def chance(self, p: float) -> bool:
        return self.r.random() < p

    def minutes(self, lo: float, hi: float) -> timedelta:
        return timedelta(minutes=self.r.uniform(lo, hi))

    def txn(self, i: int, now: datetime, age: timedelta, status: str, debited: bool, code: str | None) -> TxnRecord:
        name, vpa = self.r.choice(PAYEES)
        amount = self.r.choice([100, 1000, 4900, 12000, 22000, 35000, 49900, 149900, 250000])
        return TxnRecord(id=f"sim_{i:05d}", upi_ref=f"9{i:011d}", user_id=f"su_{i % 997}", direction="OUT",
                         payee_vpa=vpa, payee_name=name, amount_paise=amount, status=status, debited=debited,
                         failure_code=code, initiated_at=now - age)

    @staticmethod
    def npci(status, final=True, code=None) -> NpciEvidence:
        return NpciEvidence(status=status, final=final, reason_code=code)

    @staticmethod
    def ledger(t: TxnRecord, state: str, count: int | None = None, amount: int | None = None,
               reversed_after: timedelta | None = None) -> LedgerEvidence:
        if state == "NO_DEBIT":
            return LedgerEvidence(state="NO_DEBIT")
        at = t.initiated_at + timedelta(seconds=5)
        return LedgerEvidence(state=state, debit_count=count or 1, amount_paise=amount or t.amount_paise,
                              debited_at=at, reversed_at=at + (reversed_after or timedelta(hours=3))
                              if state == "REVERSED" else None)

    @staticmethod
    def merchant(credited: bool, count: int | None = None) -> MerchantEvidence:
        return MerchantEvidence(credited=credited, credit_count=count if count is not None else int(credited),
                                credited_at=None)

    def case(self, i, variant, truth, acceptable, t, now, n, l, m, **kw) -> SimCase:
        return SimCase(id=t.id, variant=variant, truth=truth, acceptable=set(acceptable), txn=t, now=now,
                       at_decision=World(n, l, m), **kw)

    # ---------------------------------------------------------------- one generator per class
    def f1(self, i, now):
        code = self.r.choice(DECLINE_CODES)
        recent = self.chance(0.15)
        t = self.txn(i, now, self.minutes(2.5, 25) if recent else self.minutes(35, 600), "FAILED", False, code)
        n, l, m = self.npci("FAILED", True, code), self.ledger(t, "NO_DEBIT"), self.merchant(False)
        if recent:
            return self.case(i, "f1_inside_pending_window", C.F1_DECLINED_PRE_DEBIT, {Action.WAIT}, t, now, n, l, m,
                             retry_unsafe=False)
        if self.chance(self.cfg.p_state_change * 2):
            # A late debit lands between the decision and the retry offer: now debited, not credited.
            after = World(self.npci("FAILED", True, code), self.ledger(t, "DEBITED"), m)
            return self.case(i, "f1_late_debit_before_offer", C.F4_DEBIT_NO_CREDIT, {Action.WAIT}, t, now, n, l, m,
                             at_action=after)
        return self.case(i, "f1_declined", C.F1_DECLINED_PRE_DEBIT, {Action.OFFER_RETRY}, t, now, n, l, m,
                         retry_unsafe=False)

    def f2(self, i, now):
        code = self.r.choice(TIMEOUT_CODES)
        t = self.txn(i, now, self.minutes(35, 600), "FAILED", False, code)
        l, m = self.ledger(t, "NO_DEBIT"), self.merchant(False)
        if self.chance(0.25):
            return self.case(i, "f2_not_final_yet", C.F2_TIMEOUT_PRE_DEBIT, {Action.WAIT}, t, now,
                             self.npci("FAILED", False, code), l, m, retry_unsafe=True)
        return self.case(i, "f2_timeout", C.F2_TIMEOUT_PRE_DEBIT, {Action.OFFER_RETRY}, t, now,
                         self.npci("FAILED", True, code), l, m, retry_unsafe=False)

    def f3(self, i, now):
        if self.chance(self.cfg.p_settling / 0.10):
            # Record says FAILED, NPCI already says SUCCESS: a disagreement still inside the lag.
            t = self.txn(i, now, timedelta(seconds=self.r.uniform(20, 100)), "FAILED", False, "TXN_FAILED")
            return self.case(i, "f3_settling_inside_lag", C.F3_PENDING, {Action.WAIT}, t, now,
                             self.npci("SUCCESS", True), self.ledger(t, "NO_DEBIT"), self.merchant(False))
        # The "Bad Network" trap: the app shows FAILED while NPCI is still pending.
        record_failed = self.chance(self.cfg.p_record_stale)
        t = self.txn(i, now, self.minutes(3, 240), "FAILED" if record_failed else "PENDING", False,
                     "BAD_NETWORK" if record_failed else None)
        return self.case(i, "f3_pending_record_says_failed" if record_failed else "f3_pending", C.F3_PENDING,
                         {Action.WAIT}, t, now, self.npci("PENDING", False), self.ledger(t, "NO_DEBIT"),
                         self.merchant(False))

    def f4(self, i, now):
        npci_status = "PENDING" if self.chance(0.2) else "FAILED"
        code = "BENEFICIARY_CREDIT_FAILED" if npci_status == "FAILED" else None
        late = self.chance(0.45)
        # debit 2-20 h ago (before the T+1 deadline) or 2-5 days ago (past it)
        age = timedelta(days=self.r.uniform(2.2, 5)) if late else self.minutes(120, 1200)
        stale = self.chance(self.cfg.p_record_stale)
        t = self.txn(i, now, age, "FAILED", not stale, code)
        n, l, m = self.npci(npci_status, npci_status == "FAILED", code), self.ledger(t, "DEBITED"), self.merchant(False)
        if not late:
            return self.case(i, "f4_before_deadline" + ("_stale_record" if stale else ""), C.F4_DEBIT_NO_CREDIT,
                             {Action.WAIT}, t, now, n, l, m)
        if self.chance(self.cfg.p_state_change * 2):
            # The reversal lands just before the dispute would be raised.
            after = World(n, self.ledger(t, "REVERSED", reversed_after=age - timedelta(minutes=1)), m)
            return self.case(i, "f4_reversal_lands_before_dispute", C.F8_ALREADY_REVERSED, {Action.CLOSE},
                             t, now, n, l, m, at_action=after, retry_unsafe=True)
        return self.case(i, "f4_deadline_missed" + ("_stale_record" if stale else ""), C.F4_DEBIT_NO_CREDIT,
                         {Action.RAISE_DISPUTE}, t, now, n, l, m, sla_breach=True)

    def f5(self, i, now):
        stale = self.chance(0.5)  # record never left PENDING, or even shows FAILED
        status = self.r.choice(["PENDING", "FAILED"]) if stale else "SUCCESS"
        t = self.txn(i, now, self.minutes(10, 600), status, status == "SUCCESS",
                     "BAD_NETWORK" if status == "FAILED" else None)
        return self.case(i, "f5_deemed_success" + ("_stale_record" if stale else ""), C.F5_DEEMED_SUCCESS,
                         {Action.CLOSE}, t, now, self.npci(self.r.choice(["DEEMED", "SUCCESS"]), True),
                         self.ledger(t, "DEBITED"), self.merchant(True))

    def f6(self, i, now):
        code = self.r.choice(BANK_DOWN_CODES)
        t = self.txn(i, now, self.minutes(1, 90), "FAILED", False, code)
        return self.case(i, "f6_bank_down", C.F6_BANK_DOWNTIME, {Action.WAIT}, t, now, self.npci("FAILED", True, code),
                         self.ledger(t, "NO_DEBIT"), self.merchant(False), outage=True)

    def f7(self, i, now):
        t = self.txn(i, now, self.minutes(30, 1440), "SUCCESS", True, None)
        return self.case(i, "f7_duplicate_debit", C.F7_DUPLICATE_DEBIT, {Action.RAISE_DISPUTE}, t, now,
                         self.npci("SUCCESS", True), self.ledger(t, "DEBITED", count=2), self.merchant(True, 1))

    def f8(self, i, now):
        stale = self.chance(0.6)  # the record still says "debited"
        age = timedelta(days=self.r.uniform(0.2, 4))
        t = self.txn(i, now, age, "FAILED", stale, "BENEFICIARY_CREDIT_FAILED")
        return self.case(i, "f8_reversed" + ("_stale_record" if stale else ""), C.F8_ALREADY_REVERSED,
                         {Action.CLOSE}, t, now, self.npci("FAILED", True, "BENEFICIARY_CREDIT_FAILED"),
                         self.ledger(t, "REVERSED", reversed_after=age / 2), self.merchant(False))

    def f9(self, i, now):
        kind = self.r.choice(["npci_success_no_debit", "credit_without_debit", "amount_mismatch",
                              "record_success_npci_failed"])
        age = self.minutes(10, 1440)
        if kind == "record_success_npci_failed":
            t = self.txn(i, now, age, "SUCCESS", True, None)
            n, l, m = self.npci("FAILED", True, "TXN_FAILED"), self.ledger(t, "NO_DEBIT"), self.merchant(False)
        elif kind == "amount_mismatch":
            t = self.txn(i, now, age, "FAILED", True, "BENEFICIARY_CREDIT_FAILED")
            n, l, m = (self.npci("FAILED", True, "BENEFICIARY_CREDIT_FAILED"),
                       self.ledger(t, "DEBITED", amount=t.amount_paise * 10), self.merchant(False))
        else:
            t = self.txn(i, now, age, "FAILED", False, "TXN_FAILED")
            n = self.npci("SUCCESS", True) if kind == "npci_success_no_debit" else self.npci("FAILED", True, "TXN_FAILED")
            l, m =self.ledger(t, "NO_DEBIT"), self.merchant(True)
        return self.case(i, f"f9_{kind}", C.F9_CONFLICT, {Action.ESCALATE}, t, now, n, l, m)

    def f10(self, i, now):
        kind = self.r.choice(["claim_amount", "claim_payee", "repeat_claimant"])
        # Looks like an ordinary debited-not-credited case, apart from the claim.
        t = self.txn(i, now, self.minutes(60, 1200), "FAILED", True, "BENEFICIARY_CREDIT_FAILED")
        n, l, m = self.npci("FAILED", True, "BENEFICIARY_CREDIT_FAILED"), self.ledger(t, "DEBITED"), self.merchant(False)
        claims, rcc = [], 0
        if kind == "claim_amount":
            claims = [Claim(kind="AMOUNT", value=str(t.amount_paise * self.r.choice([5, 10, 20])))]
        elif kind == "claim_payee":
            other = self.r.choice([p for p in PAYEES if p[0] != t.payee_name])[0]
            claims = [Claim(kind="PAYEE", value=other)]
        else:
            rcc = self.r.randint(3, 8)
        return self.case(i, f"f10_{kind}", C.F10_SUSPICIOUS, {Action.ESCALATE}, t, now, n, l, m,
                         claims=claims, recent_claim_count=rcc)

    # ---------------------------------------------------------------- noise applied on top
    def source_outage(self, c: SimCase) -> SimCase:
        """NPCI or the bank ledger is unreachable. Nothing that moves money or closes the case is
        safe without it: waiting or a human are the only acceptable answers."""
        w = c.at_decision
        if self.chance(0.5):
            w.npci = NpciEvidence(available=False)
        else:
            w.ledger = LedgerEvidence(available=False)
        c.at_action = None
        c.variant += "+source_outage"
        c.acceptable = {Action.WAIT, Action.ESCALATE}
        c.retry_unsafe, c.sla_breach = True, False
        return c

    def generate(self) -> list[SimCase]:
        classes, weights = zip(*self.cfg.mix.items())
        fns = {C.F1_DECLINED_PRE_DEBIT: self.f1, C.F2_TIMEOUT_PRE_DEBIT: self.f2, C.F3_PENDING: self.f3,
               C.F4_DEBIT_NO_CREDIT: self.f4, C.F5_DEEMED_SUCCESS: self.f5, C.F6_BANK_DOWNTIME: self.f6,
               C.F7_DUPLICATE_DEBIT: self.f7, C.F8_ALREADY_REVERSED: self.f8, C.F9_CONFLICT: self.f9,
               C.F10_SUSPICIOUS: self.f10}
        out = []
        for i in range(self.cfg.n_cases):
            cls = self.r.choices(classes, weights)[0]
            now = self.base_now - timedelta(minutes=self.r.uniform(0, 7 * 1440))
            c = fns[cls](i, now)
            if cls not in (C.F9_CONFLICT, C.F10_SUSPICIOUS) and self.chance(self.cfg.p_source_outage):
                c = self.source_outage(c)
            out.append(c)
        return out


def generate(cfg: SimConfig, base_now: datetime | None = None) -> list[SimCase]:
    """Deterministic for a given config (seed) and base time."""
    return _Gen(cfg, base_now or datetime(2026, 10, 3, 9, 0, 0)).generate()
