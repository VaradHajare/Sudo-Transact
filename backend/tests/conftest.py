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
        SCHEDULER_ENABLED=False,  # tests drive jobs explicitly; test_scheduler starts the thread itself
    )


@pytest.fixture
def client(settings):
    """App with the demo seed loaded."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings.model_copy(update={"SEED_DEMO_DATA": True}))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session(settings):
    from app.bootstrap import init_database

    engine, SessionLocal = init_database(settings)
    with SessionLocal() as db:
        yield db
    engine.dispose()
