"""Delete the SQLite file and re-seed the demo data.

Usage (from backend/):  .venv/Scripts/python scripts/reset_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import providers  # noqa: E402
from app.bootstrap import init_database  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Case, Transaction  # noqa: E402


def main() -> None:
    settings = get_settings().model_copy(update={"SEED_DEMO_DATA": True})
    # Same providers as the server, so seeded escalations (S3) queue their LLM case summary.
    # Seeding itself makes no external calls; the server's worker runs that job.
    providers.install(providers.from_settings(settings))
    engine, SessionLocal = init_database(settings, reset=True)
    with SessionLocal() as db:
        print(f"Reset {settings.sqlite_path}")
        print(f"{db.query(Transaction).count()} transactions seeded. Prepared cases:")
        for c in db.query(Case).order_by(Case.txn_id).all():
            print(f"  {c.txn_id:<22} {c.id:<12} {c.class_ or '-':<22} {c.decision or '-':<14} {c.state}")
    engine.dispose()


if __name__ == "__main__":
    main()
