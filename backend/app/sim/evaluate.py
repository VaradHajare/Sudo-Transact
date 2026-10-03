"""Baselines and metrics (spec 13).

  B0: rules on the Paytm transaction record only (the external sources are inferred from it)
  B1: B0 + NPCI status + bank ledger + merchant credit, with the live re-check before actions
  B2: B1 + the LLM classifier for AMBIGUOUS cases (the full system)

Every baseline runs the real engine functions (assemble, diagnose, decide, retry gate). The loop
mirrors `pipeline.process_transaction`: decide, re-check before OFFER_RETRY / RAISE_DISPUTE / CLOSE,
and on a change re-assemble and decide again (rule 0). `dbcheck` confirms the two agree.
"""
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable

from app.config import Settings
from app.domain import (Action, CaseClass as C, Diagnosis, EvidenceBundle, LedgerEvidence, MerchantEvidence,
                        NpciEvidence, RetryHistory)
from app.engine.decision import decide
from app.engine.diagnosis import diagnose
from app.engine.evidence import assemble
from app.sim.generator import SimCase, World

ACTIONS_NEEDING_RECHECK = {Action.OFFER_RETRY, Action.RAISE_DISPUTE, Action.CLOSE}
BASELINES = ("B0", "B1", "B2")
Classifier = Callable[[EvidenceBundle], tuple[Diagnosis | None, dict]]


@dataclass
class CaseResult:
    case: SimCase
    predicted: str  # effective class the decision used (AMBIGUOUS when unclassified / low confidence)
    action: Action
    rule: str
    compensation: bool
    first_action: Action  # before the live re-check
    recheck_cancelled: bool
    llm_used: bool
    llm_confidence: float | None = None

    @property
    def correct(self) -> bool:
        return self.action in self.case.acceptable


def record_only_world(c: SimCase) -> World:
    """B0: what the Paytm record alone implies about the outside world."""
    t = c.txn
    debit = LedgerEvidence(state="DEBITED", debit_count=1, amount_paise=t.amount_paise, debited_at=t.initiated_at)
    if t.status == "SUCCESS":
        return World(NpciEvidence(status="SUCCESS", final=True), debit, MerchantEvidence(credited=True, credit_count=1))
    npci = (NpciEvidence(status="FAILED", final=True, reason_code=t.failure_code) if t.status == "FAILED"
            else NpciEvidence(status="PENDING", final=False))
    return World(npci, debit if t.debited else LedgerEvidence(state="NO_DEBIT"), MerchantEvidence(credited=False))


def _bundle(c: SimCase, w: World, settings: Settings) -> EvidenceBundle:
    return assemble(c.txn, w.npci, w.ledger, w.merchant, now=c.now, settings=settings, claims=c.claims,
                    recent_claim_count=c.recent_claim_count)


def run_case(c: SimCase, baseline: str, settings: Settings, classifier: Classifier | None = None) -> CaseResult:
    hist = RetryHistory()
    use_llm = baseline == "B2" and classifier is not None

    def diag(b: EvidenceBundle) -> tuple[Diagnosis, bool]:
        d = diagnose(b, settings)
        if use_llm and d.case_class == C.AMBIGUOUS:
            llm_d, _ = classifier(b)
            if llm_d:
                return llm_d, True
        return d, False

    world = record_only_world(c) if baseline == "B0" else c.at_decision
    b = _bundle(c, world, settings)
    d, llm_used = diag(b)
    dec = decide(d, b, c.now, settings, hist)
    first, cancelled = dec.action, False
    # Live re-check (8.5). B0 has nothing to re-check: it only knows the record.
    if baseline != "B0" and dec.action in ACTIONS_NEEDING_RECHECK and c.at_action is not None:
        cancelled = True  # the world changed since the decision: rule 0, re-assemble and decide again
        b = _bundle(c, c.at_action, settings)
        d, llm_used2 = diag(b)
        llm_used = llm_used or llm_used2
        dec = decide(d, b, c.now, settings, hist)
    effective = d.case_class if d.confidence >= settings.LLM_MIN_CONFIDENCE else C.AMBIGUOUS
    return CaseResult(case=c, predicted=str(effective), action=dec.action, rule=dec.rule,
                      compensation=dec.compensation, first_action=first, recheck_cancelled=cancelled,
                      llm_used=llm_used, llm_confidence=d.confidence if llm_used else None)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def metrics(results: list[CaseResult], min_confidence: float = 0.7) -> dict:
    n = len(results)
    by_truth: dict[str, list[CaseResult]] = defaultdict(list)
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        by_truth[str(r.case.truth)].append(r)
        confusion[str(r.case.truth)][r.predicted] += 1

    unsafe = [r for r in results if r.case.retry_unsafe]
    retries = [r for r in results if r.action == Action.OFFER_RETRY]
    false_retries = [r for r in retries if r.case.retry_unsafe]
    money_actions = [r for r in results if r.action in (Action.CLOSE, Action.RAISE_DISPUTE)]
    false_actions = [r for r in money_actions if not r.correct]
    escalations = [r for r in results if r.action == Action.ESCALATE]
    must_escalate = [r for r in results if r.case.acceptable == {Action.ESCALATE}]
    cancelled = [r for r in results if r.recheck_cancelled]
    prevented = [r for r in cancelled if r.first_action not in r.case.acceptable]
    breaches = [r for r in results if r.case.sla_breach]
    outage = [r for r in results if r.case.outage]
    llm = [r for r in results if r.llm_used]

    failures = Counter(r.case.variant for r in results if not r.correct)
    wrong_examples = defaultdict(Counter)
    for r in results:
        if not r.correct:
            wrong_examples[r.case.variant][f"{r.action} (rule {r.rule})"] += 1

    return {
        "n_cases": n,
        "diagnosis_accuracy": _rate(sum(r.predicted == str(r.case.truth) for r in results), n),
        "diagnosis_accuracy_per_class": {k: _rate(sum(r.predicted == k for r in v), len(v))
                                         for k, v in sorted(by_truth.items())},
        "action_accuracy": _rate(sum(r.correct for r in results), n),
        "action_accuracy_per_class": {k: _rate(sum(r.correct for r in v), len(v)) for k, v in sorted(by_truth.items())},
        "retries_offered": len(retries),
        "false_retries": len(false_retries),
        "false_retry_rate": _rate(len(false_retries), len(unsafe)),  # over cases where a retry is unsafe
        "false_actions": len(false_actions),
        "false_action_rate": _rate(len(false_actions), len(money_actions)),  # wrong close / dispute
        "recheck_cancelled": len(cancelled),
        "recheck_prevented_wrong_action": len(prevented),
        "escalations": len(escalations),
        "escalation_rate": _rate(len(escalations), n),
        # precision: escalating was an acceptable answer (needed, or a safe choice with a source down)
        "escalation_precision": _rate(sum(Action.ESCALATE in r.case.acceptable for r in escalations), len(escalations)),
        "needless_escalations": sum(Action.ESCALATE not in r.case.acceptable for r in escalations),
        "escalation_recall": _rate(sum(r.action == Action.ESCALATE for r in must_escalate), len(must_escalate)),
        "sla_breaches": len(breaches),
        "sla_breaches_caught": sum(r.action == Action.RAISE_DISPUTE and r.compensation for r in breaches),
        "outage_cases": len(outage),
        "outage_answered_without_human": sum(r.action != Action.ESCALATE for r in outage),
        "llm_classified": len(llm),
        "llm_low_confidence": sum(1 for r in llm if (r.llm_confidence or 0) < min_confidence),
        "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
        "failures_by_variant": dict(failures.most_common()),
        "wrong_actions_by_variant": {k: dict(v) for k, v in wrong_examples.items()},
    }


class CachedClassifier:
    """Wraps the live LLM classifier. Cached by the exact structured input it sees, so thousands of
    cases cost one call per distinct evidence pattern."""

    def __init__(self, llm):
        from app.conversation import llm_tasks
        self.llm, self.tasks = llm, llm_tasks
        self.cache: dict[str, tuple[Diagnosis | None, dict]] = {}
        self.calls, self.latency_ms, self.errors = 0, [], 0

    def __call__(self, b: EvidenceBundle) -> tuple[Diagnosis | None, dict]:
        key = self.tasks.classify_payload(b)
        if key not in self.cache:
            out, meta = self.llm.complete_json(self.tasks.CLASSIFY_SYSTEM, key, self.tasks.ClassOut)
            self.calls += 1
            self.latency_ms.append(meta.latency_ms)
            self.errors += 0 if out else 1
            d = Diagnosis(case_class=out.case_class, confidence=out.confidence, source="LLM",
                          reasons=out.reasons) if out else None
            self.cache[key] = (d, {"ok": meta.ok, "error": meta.error})
        return self.cache[key]

    def stats(self) -> dict:
        lat = sorted(self.latency_ms)
        return {"distinct_inputs": len(self.cache), "calls": self.calls, "errors": self.errors,
                "latency_ms_median": lat[len(lat) // 2] if lat else None,
                "answers": [{"input": json.loads(k),
                             "class": str(d.case_class) if d else None,
                             "confidence": d.confidence if d else None} for k, (d, _) in self.cache.items()]}


def run_baselines(cases: list[SimCase], settings: Settings, classifier: Classifier | None) -> dict:
    out = {}
    for bl in BASELINES:
        if bl == "B2" and classifier is None:
            out[bl] = None  # not run: no LLM configured
            continue
        out[bl] = metrics([run_case(c, bl, settings, classifier) for c in cases], settings.LLM_MIN_CONFIDENCE)
    return out
