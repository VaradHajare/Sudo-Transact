"""Simulator + B0/B1/B2 evaluation (spec 12-13).

Usage (from backend/):
  .venv/Scripts/python scripts/run_sim.py                  # 3000 cases, B2 with the configured LLM
  .venv/Scripts/python scripts/run_sim.py --no-llm         # B0 / B1 only, no network
  .venv/Scripts/python scripts/run_sim.py --n 5000 --seed 11

Writes docs/evaluation.json and docs/EVALUATION.md, and records the run in sim_runs / sim_cases.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import providers  # noqa: E402
from app.bootstrap import init_database  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.sim.generator import SimConfig  # noqa: E402
from app.sim.runner import run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-llm", action="store_true", help="skip B2 (no LLM calls)")
    ap.add_argument("--db-sample", type=int, default=500, help="cases also run through the real DB pipeline")
    ap.add_argument("--attach-users", type=int, default=50, help="users in the right-payment check")
    a = ap.parse_args()

    logging.getLogger().setLevel(logging.WARNING)
    settings = get_settings()
    providers.install(providers.from_settings(settings))
    engine, SessionLocal = init_database(settings)
    with SessionLocal() as db:
        r = run(SimConfig(n_cases=a.n, seed=a.seed), settings, use_llm=not a.no_llm, db_sample=a.db_sample,
                attach_users=a.attach_users, db=db)
    engine.dispose()

    print()
    print(f"{'':34}{'B0':>10}{'B1':>10}{'B2':>10}")
    for key in ("false_retry_rate", "false_retries", "false_action_rate", "action_accuracy", "diagnosis_accuracy",
                "escalation_rate", "recheck_cancelled", "llm_classified"):
        cells = []
        for bl in ("B0", "B1", "B2"):
            m = r["baselines"].get(bl)
            v = None if m is None else m.get(key)
            cells.append("-" if v is None else (f"{v * 100:.1f}%" if isinstance(v, float) else str(v)))
        print(f"{key:34}" + "".join(f"{c:>10}" for c in cells))
    if r["baselines"]["B1"]["false_retries"] or (r["baselines"].get("B2") or {}).get("false_retries"):
        print("\nFALSE RETRIES > 0: treat as a bug (spec 13.3)")
        sys.exit(1)


if __name__ == "__main__":
    main()
