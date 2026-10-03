"""OpenAI-compatible chat client (DeepSeek by default; Sarvam's LLM or Claude can replace it via
LLM_BASE_URL / LLM_MODEL / LLM_API_KEY). JSON output is always validated with Pydantic; any
failure returns None and the caller falls back to rules / templates."""
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger("llm")
T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass
class LLMMeta:
    ok: bool
    latency_ms: int
    error: str | None = None
    model: str | None = None


def extract_json(text: str) -> str | None:
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else None


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.http = httpx.Client(base_url=settings.LLM_BASE_URL.rstrip("/"), timeout=settings.LLM_TIMEOUT_SECONDS,
                                 headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"}, transport=transport)

    def chat(self, system: str, user: str, *, json_out: bool = False,
             temperature: float = 0.0) -> tuple[str | None, LLMMeta]:
        # One budget for every call: reasoning models (deepseek-flash) spend part of max_tokens on
        # hidden reasoning, and a small budget returns empty content with finish_reason "length".
        body = {"model": self.settings.LLM_MODEL, "temperature": temperature,
                "max_tokens": self.settings.LLM_MAX_TOKENS,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_out and self.settings.LLM_JSON_MODE:
            body["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        try:
            r = self.http.post("/chat/completions", json=body)
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            latency = int((time.perf_counter() - t0) * 1000)
            if not content.strip():
                why = "truncated (raise LLM_MAX_TOKENS)" if choice.get("finish_reason") == "length" else "empty content"
                return None, LLMMeta(ok=False, latency_ms=latency, error=why, model=data.get("model"))
            return content, LLMMeta(ok=True, latency_ms=latency, model=data.get("model"))
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            log.warning("LLM call failed: %s", type(e).__name__)
            return None, LLMMeta(ok=False, latency_ms=int((time.perf_counter() - t0) * 1000),
                                 error=f"{type(e).__name__}: {str(e)[:200]}")

    def complete_json(self, system: str, user: str, schema: type[T], **kw) -> tuple[T | None, LLMMeta]:
        content, meta = self.chat(system, user, json_out=True, **kw)
        if content is None:
            return None, meta
        raw = extract_json(content)
        try:
            return schema.model_validate(json.loads(raw or "")), meta
        except (ValidationError, json.JSONDecodeError) as e:
            meta.ok, meta.error = False, f"invalid JSON output: {type(e).__name__}"
            return None, meta
