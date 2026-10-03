"""Outbound reports to the owner: WhatsApp via CallMeBot, and/or a generic JSON webhook (Zapier,
Make, n8n...). Called only from the background job FAILURE_REPORT, never from a user request.

CallMeBot's free API is for personal notifications to your own number: add +34 644 99 26 98 on
WhatsApp, send "I allow callmebot to send me messages", and put the API key it replies with in
backend/.env (CALLMEBOT_API_KEY) with your number (WHATSAPP_REPORT_PHONE).
"""
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import Settings

log = logging.getLogger("notify")
WHATSAPP_MAX_CHARS = 1500  # keep reports short; long WhatsApp messages get split or dropped


class NotifyError(Exception):
    pass


@dataclass
class SendResult:
    channels: list[str] = field(default_factory=list)  # e.g. ["whatsapp", "webhook"]
    latency_ms: int = 0


class Notifier:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.http = httpx.Client(timeout=settings.REPORT_TIMEOUT_SECONDS, transport=transport)

    @property
    def whatsapp_on(self) -> bool:
        s = self.settings
        return bool(s.WHATSAPP_REPORTS_ENABLED and s.WHATSAPP_REPORT_PHONE and s.CALLMEBOT_API_KEY)

    @property
    def webhook_on(self) -> bool:
        return bool(self.settings.REPORT_WEBHOOK_URL)

    def send_report(self, text: str, payload: dict) -> SendResult:
        """Send to every configured channel. Raises NotifyError if any of them fails (the job retries;
        a channel that already succeeded may then send twice, which is fine for a notification)."""
        t0 = time.perf_counter()
        out = SendResult()
        if self.whatsapp_on:
            self._whatsapp(text[:WHATSAPP_MAX_CHARS])
            out.channels.append("whatsapp")
        if self.webhook_on:
            self._webhook({**payload, "text": text})
            out.channels.append("webhook")
        out.latency_ms = int((time.perf_counter() - t0) * 1000)
        return out

    def _whatsapp(self, text: str) -> None:
        s = self.settings
        try:
            r = self.http.get(s.CALLMEBOT_BASE_URL, params={
                "phone": s.WHATSAPP_REPORT_PHONE, "text": text, "apikey": s.CALLMEBOT_API_KEY})
        except httpx.HTTPError as e:
            raise NotifyError(f"whatsapp: {type(e).__name__}") from e
        body = r.text.lower()
        # CallMeBot answers 200 with an HTML page; failures say so in the body
        if r.status_code != 200 or "error" in body or "apikey is invalid" in body:
            raise NotifyError(f"whatsapp: HTTP {r.status_code}: {r.text[:120]}")

    def _webhook(self, payload: dict) -> None:
        try:
            r = self.http.post(self.settings.REPORT_WEBHOOK_URL, json=payload)
        except httpx.HTTPError as e:
            raise NotifyError(f"webhook: {type(e).__name__}") from e
        if r.status_code >= 300:
            raise NotifyError(f"webhook: HTTP {r.status_code}")
