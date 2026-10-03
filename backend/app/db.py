"""SQLite engine. WAL + busy timeout on every connection (API and scheduler write at the same time)."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str, busy_timeout_ms: int = 5000) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


# case_events is an append-only audit log (spec 7): block UPDATE and DELETE at the DB level.
AUDIT_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS case_events_no_update BEFORE UPDATE ON case_events
       BEGIN SELECT RAISE(ABORT, 'case_events is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS case_events_no_delete BEFORE DELETE ON case_events
       BEGIN SELECT RAISE(ABORT, 'case_events is append-only'); END""",
]


def create_schema(engine: Engine) -> None:
    from app import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for stmt in AUDIT_TRIGGERS:
            conn.execute(text(stmt))


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
