"""Create the schema and (optionally) seed demo data."""
import logging

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import create_schema, make_engine, make_sessionmaker
from app.models import User

log = logging.getLogger("bootstrap")


def delete_db_files(settings: Settings) -> None:
    path = settings.sqlite_path
    if not path:
        return
    for suffix in ("", "-wal", "-shm"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()


def prepare_cases(db: Session, settings: Settings, txn_ids: list[str]) -> None:
    """Background preparation: assemble + decide every failed/pending payment before the user asks."""
    from app.engine.pipeline import process_transaction

    for txn_id in txn_ids:
        process_transaction(db, settings, txn_id, trigger="SEED")


def seed_if_empty(SessionLocal: sessionmaker, settings: Settings) -> bool:
    from app.seed import seed_demo

    with SessionLocal() as db:
        if db.query(User).first() is not None:
            return False
        problem_ids = seed_demo(db)
        prepare_cases(db, settings, problem_ids)
        db.commit()
    return True


def init_database(settings: Settings, reset: bool = False):
    if reset:
        delete_db_files(settings)
    if settings.sqlite_path:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.DATABASE_URL, settings.SQLITE_BUSY_TIMEOUT_MS)
    create_schema(engine)
    SessionLocal = make_sessionmaker(engine)
    if settings.SEED_DEMO_DATA and seed_if_empty(SessionLocal, settings):
        log.info("seeded demo data")
    return engine, SessionLocal
