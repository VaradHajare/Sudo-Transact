import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Isolated settings: temp SQLite file, everything external off, no .env influence."""
    return Settings(
        _env_file=None,
        DATABASE_URL=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        SEED_DEMO_DATA=False,
        LLM_ENABLED=False, STT_ENABLED=False, TTS_ENABLED=False,
        SESSION_TOKEN_SECRET="test-secret",
    )


@pytest.fixture
def db_session(settings):
    from app.bootstrap import init_database

    engine, SessionLocal = init_database(settings)
    with SessionLocal() as db:
        yield db
    engine.dispose()
