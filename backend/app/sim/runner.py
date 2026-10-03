"""Run the simulator end to end: generate, evaluate B0/B1/B2, run the DB checks, persist the run
(sim_runs / sim_cases), and write docs/evaluation.json + docs/EVALUATION.md."""
import json
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app import clock, providers
from app.config import REPO_DIR, Settings
from app.models import SimCase as SimCaseRow, SimRun
from app.sim import dbcheck
from app.sim.evaluate import CachedClassifier, run_baselines
from app.sim.generator import SimConfig, generate
from app.sim.report import render_markdown

REPORT_JSON = REPO_DIR / "docs" / "evaluation.json"
REPORT_MD = REPO_DIR / "docs" / "EVALUATION.md"


def run(cfg: SimConfig, settings: Settings, *, use_llm: bool, db_sample: int, attach_users: int,
        db: Session | None = None, write_files: bool = True, log=print) -> dict:
    t0 = time.perf_counter()
    cases = generate(cfg)
    log(f"generated {len(cases)} cases (seed {cfg.seed})")

    classifier = None
    p = providers.current()
    if use_llm and p.llm is not None:
        classifier = CachedClassifier(p.llm)
    elif use_llm:
        log("LLM not configured (LLM_ENABLED / LLM_API_KEY): B2 is skipped")
    baselines = run_baselines(cases, settings, classifier)
    log("baselines done" + (f" ({classifier.calls} LLM calls)" if classifier else ""))

    agreement = dbcheck.pipeline_agreement(cases[:db_sample], settings) if db_sample else None
    attachment = dbcheck.right_payment_attachment(settings, attach_users) if attach_users else None
    log("database checks done")

    report = {
        "generated_at": clock.real_utcnow().isoformat(timespec="seconds") + "Z",
        "config": cfg.to_json(),
        "rules": {k: getattr(settings, k) for k in ("PENDING_WINDOW_MINUTES", "RETRY_COOLDOWN_SECONDS",
                                                    "EVIDENCE_LAG_SECONDS", "SLA_BENEFICIARY_CREDIT_FAILURE_DAYS",
                                                    "LLM_MIN_CONFIDENCE", "REPEAT_CLAIM_THRESHOLD")},
        "llm": ({"model": settings.LLM_MODEL, **classifier.stats()} if classifier else None),
        "variants": _variant_counts(cases),
        "baselines": baselines,
        "pipeline_agreement": agreement,
        "right_payment": attachment,
        "seconds": round(time.perf_counter() - t0, 1),
    }
    if db is not None:
        report["run_id"] = persist(db, cfg, cases, report)
    if write_files:
        REPORT_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
        log(f"wrote {REPORT_JSON.relative_to(REPO_DIR)} and {REPORT_MD.relative_to(REPO_DIR)}")
    return report


def _variant_counts(cases) -> dict:
    out: dict[str, int] = {}
    for c in cases:
        out[c.variant] = out.get(c.variant, 0) + 1
    return dict(sorted(out.items()))


def persist(db: Session, cfg: SimConfig, cases, report: dict) -> int:
    summary = {k: v for k, v in report.items() if k not in ("variants",)}
    run_row = SimRun(config_json=json.dumps({"config": cfg.to_json(), "summary": summary}, default=str),
                     started_at=datetime.fromisoformat(report["generated_at"].rstrip("Z")))
    db.add(run_row)
    db.flush()
    db.bulk_save_objects([SimCaseRow(run_id=run_row.id, ground_truth_class=str(c.truth), txn_id=c.id,
                                     expected_action=c.expected_action) for c in cases])
    db.commit()
    return run_row.id
