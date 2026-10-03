"""FastAPI app: /v1 API, /mock world, and the web UI served as static files at /.

Run (from backend/):  .venv/Scripts/python -m uvicorn app.main:app --port 8000
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import i18n, providers
from app.bootstrap import init_database
from app.config import Settings, get_settings
from app.scheduler import Worker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = None
        if settings.SCHEDULER_ENABLED:
            worker = Worker(app.state.SessionLocal, settings)
            worker.start()
        app.state.worker = worker
        yield
        if worker:
            worker.stop()
        app.state.engine.dispose()

    app = FastAPI(title="Sudo Transact backend", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    providers.install(providers.from_settings(settings))
    app.state.engine, app.state.SessionLocal = init_database(settings)

    @app.get("/healthz")
    def healthz():
        p = providers.current()
        return {"ok": True, "llm": p.llm is not None, "stt": settings.STT_ENABLED and p.sarvam is not None,
                "tts": settings.TTS_ENABLED and p.sarvam is not None, "scheduler": settings.SCHEDULER_ENABLED,
                "llm_rephrase": p.llm is not None and settings.LLM_REPHRASE_ENABLED}

    _include_routers(app, settings)

    @app.middleware("http")
    async def no_stale_web_files(request, call_next):
        # UI language from the app's toggle (X-UI-Lang), visible to the views and the turn handler.
        token = i18n.set_ui_lang(request.headers.get("x-ui-lang"))
        try:
            response = await call_next(request)
        finally:
            i18n.reset_ui_lang(token)
        # The UI has no build step / hashed filenames: make browsers revalidate so edits show up.
        if not request.url.path.startswith(("/v1", "/mock")):
            response.headers["Cache-Control"] = "no-cache"
        return response

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
