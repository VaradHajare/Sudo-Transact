"""FastAPI app: /v1 API, /mock world, and the web UI served as static files at /.

Run (from backend/):  .venv/Scripts/python -m uvicorn app.main:app --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bootstrap import init_database
from app.config import Settings, get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.engine.dispose()

    app = FastAPI(title="Sudo Transact backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine, app.state.SessionLocal = init_database(settings)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "llm": settings.LLM_ENABLED, "stt": settings.STT_ENABLED, "tts": settings.TTS_ENABLED}

    _include_routers(app, settings)

    web_dir = Path(settings.WEB_DIR)
    if web_dir.is_dir():
        # Mounted last so /v1 and /mock win. Same origin for UI and API: no CORS needed.
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def _include_routers(app: FastAPI, settings: Settings) -> None:
    from app.api.v1 import router as v1_router
    from app.mock.router import router as mock_router

    app.include_router(v1_router)
    if settings.DEMO_MODE:
        app.include_router(mock_router)


app = create_app()
