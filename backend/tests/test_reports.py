"""Failed-payment reports to the owner (WhatsApp via CallMeBot, and/or a webhook). No network: the
Notifier runs against a fake transport."""
import json

import httpx
import pytest

from app import providers
from app.models import Job
from app.providers.notify import Notifier
from app.scheduler import run_due_jobs


class FakeOutbound:
    def __init__(self):
        self.whatsapp, self.webhook = [], []
        self.whatsapp_body = "<p>Message queued. You will receive it in a few seconds.</p>"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.callmebot.test":
            self.whatsapp.append(dict(request.url.params))
            return httpx.Response(200, text=self.whatsapp_body)
        if request.url.host == "hooks.test":
            self.webhook.append(json.loads(request.content))
            return httpx.Response(200, json={"status": "success"})
        return httpx.Response(404)


@pytest.fixture
def out():
    return FakeOutbound()


@pytest.fixture
def rsettings(settings):
    return settings.model_copy(update={
        "SEED_DEMO_DATA": True, "WHATSAPP_REPORTS_ENABLED": True, "WHATSAPP_REPORT_PHONE": "+919876543210",
        "CALLMEBOT_API_KEY": "123456", "CALLMEBOT_BASE_URL": "https://api.callmebot.test/whatsapp.php",
        "REPORT_WEBHOOK_URL": "https://hooks.test/catch/1",
    })


@pytest.fixture
def api(rsettings, out):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(rsettings)
    providers.install(providers.Providers(notifier=Notifier(rsettings, httpx.MockTransport(out)), settings=rsettings))
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer " + c.post("/v1/session", json={}).json()["token"]
        yield c
    providers.install(providers.Providers())


def _jobs(api):
    with api.app.state.SessionLocal() as db:
        return [(j.kind, j.status) for j in db.query(Job).filter(Job.kind == "FAILURE_REPORT").all()]


def _run_jobs(api, rsettings):
    with api.app.state.SessionLocal() as db:
        return run_due_jobs(db, rsettings)


def test_seeded_demo_payments_send_no_report(api):
    assert _jobs(api) == []


def test_failed_scan_payment_sends_one_whatsapp_report(api, rsettings, out):
    qr = api.post("/v1/scan").json()
    txn = api.post("/v1/payments", json={**qr, "amount_paise": 64000, "pin": "1234", "origin": "scan"}).json()["transaction"]
    assert _jobs(api) == [("FAILURE_REPORT", "QUEUED")]
    ran = [j for j in _run_jobs(api, rsettings) if j["kind"] == "FAILURE_REPORT"]
    assert ran[0]["status"] == "DONE" and ran[0]["channels"] == ["whatsapp", "webhook"]

    (msg,) = out.whatsapp
    assert msg["phone"] == "+919876543210" and msg["apikey"] == "123456"
    text = msg["text"]
    assert "*₹640* to *Kaveri Restaurant*" in text and "UPI ref" in text
    assert "*Bank agent:* NPCI says: failed (final). ₹640 was taken from your account." in text
    assert "(F4)" in text and "*Follow-up agent:*" in text and "*Told the customer:* Yes, ₹640 was taken" in text
    assert "…" not in text  # progress lines are left out

    (hook,) = out.webhook
    assert hook["event"] == "payment_failed" and hook["txn_id"] == txn["id"] and hook["amount_paise"] == 64000
    assert [a["id"] for a in hook["agents"]] == ["bank", "rules", "followup"] and hook["text"] == text
    # once per payment: opening the chat later queues nothing new
    api.post("/v1/cases/open", json={"txn_id": txn["id"], "investigate": True})
    assert _jobs(api) == [("FAILURE_REPORT", "DONE")]


def test_escalated_payment_report_is_marked_urgent(api, rsettings, out):
    api.post("/v1/events/transactions", json={
        "payee_vpa": "omsweets@okaxis", "payee_name": "Om Sweets", "amount_paise": 20000, "status": "FAILED",
        "mock_evidence": {"npci": {"status": "SUCCESS"}, "ledger": {"state": "NO_DEBIT"}, "merchant": {"credited": True}},
        "initiated_at": "2026-10-03T03:00:00"})
    _run_jobs(api, rsettings)
    assert out.whatsapp[0]["text"].startswith("🔴 *Needs a human*")


def test_delivery_failure_retries(api, rsettings, out):
    out.whatsapp_body = "<p>APIKey is invalid. Please check your phone number and apikey.</p>"
    qr = api.post("/v1/scan").json()
    api.post("/v1/payments", json={**qr, "amount_paise": 5000, "pin": "1234", "origin": "scan"})
    ran = [j for j in _run_jobs(api, rsettings) if j["kind"] == "FAILURE_REPORT"]
    assert ran[0]["status"] in ("QUEUED", "FAILED") and "whatsapp" in (ran[0].get("error") or "")


def test_no_channel_configured_queues_nothing(client):
    qr_headers = {"Authorization": "Bearer " + client.post("/v1/session", json={}).json()["token"]}
    qr = client.post("/v1/scan", headers=qr_headers).json()
    client.post("/v1/payments", json={**qr, "amount_paise": 5000, "pin": "1234", "origin": "scan"}, headers=qr_headers)
    with client.app.state.SessionLocal() as db:
        assert db.query(Job).filter(Job.kind == "FAILURE_REPORT").count() == 0
