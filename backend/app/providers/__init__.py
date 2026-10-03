"""External providers (LLM, Sarvam STT/TTS) behind small adapters.

`current()` returns the providers configured at app start (None for anything switched off), so
the pipeline, scheduler and turn handler can use them without threading them through every call.
Tests install fakes with `install()`.
"""
from dataclasses import dataclass

from app.config import Settings


@dataclass
class Providers:
    llm: object | None = None  # app.providers.llm.LLMClient
    sarvam: object | None = None  # app.providers.sarvam.SarvamClient
    settings: Settings | None = None


_current = Providers()


def from_settings(settings: Settings) -> Providers:
    from app.providers.llm import LLMClient
    from app.providers.sarvam import SarvamClient

    llm = LLMClient(settings) if settings.LLM_ENABLED and settings.LLM_API_KEY and settings.LLM_BASE_URL else None
    sarvam = SarvamClient(settings) if (settings.STT_ENABLED or settings.TTS_ENABLED) and settings.SARVAM_API_KEY else None
    return Providers(llm=llm, sarvam=sarvam, settings=settings)


def install(p: Providers) -> None:
    global _current
    _current = p


def current() -> Providers:
    return _current
