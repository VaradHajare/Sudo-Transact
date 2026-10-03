"""Sarvam AI speech-to-text and text-to-speech.

Probed on 2026-10-03: STT accepts browser webm/opus but only with the bare MIME type
`audio/webm` (Chrome sends `audio/webm;codecs=opus`, which is rejected), so parameters are
stripped. `language_code="unknown"` auto-detects. TTS returns base64 WAV in `audios[]`.
"""
import base64
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import Settings

log = logging.getLogger("sarvam")

LANG_TO_CODE = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN"}
CODE_TO_LANG = {v: k for k, v in LANG_TO_CODE.items()}
ALLOWED_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "audio/ogg", "audio/opus",
                 "audio/webm", "video/webm", "audio/mp4", "audio/x-m4a", "audio/aac", "audio/flac", "audio/amr"}
TTS_MAX_CHARS = 2500


class ProviderError(Exception):
    pass


@dataclass
class STTResult:
    transcript: str
    language_code: str | None
    language_probability: float | None
    latency_ms: int

    @property
    def lang(self) -> str | None:
        return CODE_TO_LANG.get(self.language_code or "")


def normalize_content_type(content_type: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    return base if base in ALLOWED_TYPES else "application/octet-stream"


class SarvamClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.http = httpx.Client(base_url=settings.SARVAM_BASE_URL.rstrip("/"), timeout=30,
                                 headers={"api-subscription-key": settings.SARVAM_API_KEY}, transport=transport)

    def stt(self, audio: bytes, content_type: str | None, filename: str = "speech.webm",
            language_code: str = "unknown") -> STTResult:
        t0 = time.perf_counter()
        try:
            r = self.http.post("/speech-to-text",
                               files={"file": (filename, audio, normalize_content_type(content_type))},
                               data={"model": self.settings.SARVAM_STT_MODEL, "language_code": language_code})
            r.raise_for_status()
            d = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"stt failed: {type(e).__name__}: {_short(e)}") from None
        return STTResult(transcript=(d.get("transcript") or "").strip(), language_code=d.get("language_code"),
                         language_probability=d.get("language_probability"),
                         latency_ms=int((time.perf_counter() - t0) * 1000))

    def tts(self, text: str, lang: str) -> bytes:
        try:
            r = self.http.post("/text-to-speech", json={
                "text": text[:TTS_MAX_CHARS], "target_language_code": LANG_TO_CODE.get(lang, "en-IN"),
                "speaker": self.settings.SARVAM_TTS_SPEAKER, "model": self.settings.SARVAM_TTS_MODEL})
            r.raise_for_status()
            return base64.b64decode(r.json()["audios"][0])
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"tts failed: {type(e).__name__}: {_short(e)}") from None


def _short(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code} {e.response.text[:200]}"
    return str(e)[:200]
