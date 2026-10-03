"""Step 7: Sarvam STT/TTS + the four LLM jobs, through the real adapters with a fake network."""
import base64
import json

import httpx
import pytest

from app import providers
from app.conversation import llm_tasks
from app.engine import audit
from app.providers.llm import LLMClient
from app.providers.sarvam import SarvamClient
from app.scheduler import run_due_jobs

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt fake-audio"


class FakeNet:
    """Answers Sarvam and the OpenAI-compatible LLM. Tests tweak the fields."""

    def __init__(self):
        self.transcript = "पैसे कट गए पर मिला नहीं"
        self.stt_lang = "hi-IN"
        self.stt_status = 200
        self.stt_seen = []
        self.tts_calls = 0
        self.llm_calls = []
        self.intent = {"intent": "why", "language": "en", "confidence": 0.9}
        self.klass = {"case_class": "F3_PENDING", "confidence": 0.9, "reasons": ["NPCI unavailable, no debit"]}
        self.summary = "The issuer ledger shows no debit while NPCI reports success; confirm the debit with the bank first."
        self.rephrase = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/speech-to-text"):
            body = request.content.decode("latin-1")
            self.stt_seen.append(body)
            if self.stt_status != 200:
                return httpx.Response(self.stt_status, json={"error": {"message": "boom"}})
            return httpx.Response(200, json={"request_id": "r1", "transcript": self.transcript,
                                             "language_code": self.stt_lang, "language_probability": 0.97})
        if path.endswith("/text-to-speech"):
            self.tts_calls += 1
            return httpx.Response(200, json={"request_id": "r2", "audios": [base64.b64encode(WAV).decode()]})
        if path.endswith("/chat/completions"):
            req = json.loads(request.content)
            system = req["messages"][0]["content"]
            self.llm_calls.append(system[:40])
            if system.startswith("You label ONE message"):
                content = json.dumps(self.intent) if isinstance(self.intent, dict) else self.intent
            elif system.startswith("You are a UPI payments operations analyst"):
                content = "```json\n" + json.dumps(self.klass) + "\n```"
            elif system.startswith("You write a short note"):
                content = self.summary
            else:
                content = self.rephrase or req["messages"][1]["content"]
            return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{"message": {"content": content}}]})
        return httpx.Response(404)


@pytest.fixture
def net():
    return FakeNet()


@pytest.fixture
def vsettings(settings):
    return settings.model_copy(update={
        "SEED_DEMO_DATA": True, "LLM_ENABLED": True, "STT_ENABLED": True, "TTS_ENABLED": True,
        "LLM_API_KEY": "test", "LLM_BASE_URL": "https://llm.test/v1", "SARVAM_API_KEY": "test",
        "SARVAM_BASE_URL": "https://sarvam.test", "PUBLIC_BASE_URL": "http://localhost:8000",
        "MEDIA_DIR": str(settings.sqlite_path.parent / "media"),
    })


@pytest.fixture
def api(vsettings, net):
    from fastapi.testclient import TestClient

    from app.main import create_app

    providers.install(providers.Providers(llm=LLMClient(vsettings, httpx.MockTransport(net)),
                                          sarvam=SarvamClient(vsettings, httpx.MockTransport(net)), settings=vsettings))
    app = create_app(vsettings)
    # create_app installs clients from settings; swap in the fake network again
    providers.install(providers.Providers(llm=LLMClient(vsettings, httpx.MockTransport(net)),
                                          sarvam=SarvamClient(vsettings, httpx.MockTransport(net)), settings=vsettings))
    llm_tasks._classify_cache.clear()
    with TestClient(app) as c:
        tok = c.post("/v1/session", json={}).json()["token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        c.app_state = app.state
        yield c
    providers.install(providers.Providers())


def open_case(api, txn_id):
    return api.post("/v1/cases/open", json={"txn_id": txn_id}).json()["case"]["id"]


def say_audio(api, cid, ctype="audio/webm;codecs=opus", **kw):
    return api.post("/v1/voice/turn", data={"case_id": cid}, files={"audio": ("speech.webm", b"\x1aE\xdf\xa3opus", ctype)}, **kw)


def say(api, cid, text):
    r = api.post("/v1/voice/turn", json={"case_id": cid, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


def events(api, cid, kind):
    return [e for e in api.get(f"/v1/cases/{cid}/activity").json()["events"] if e["event"] == kind]


# ------------------------------------------------------------------ STT / TTS

def test_voice_turn_s2_hindi_with_spoken_reply(api, net):
    cid = open_case(api, "txn_s2_citymobiles")
    r = say_audio(api, cid)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["input"] == "voice" and d["lang"] == "hi" and d["user_text"] == net.transcript
    assert d["stt"]["language_code"] == "hi-IN"
    assert d["speak"]["text"].startswith("हाँ, आपके खाते से 1,499 रुपये कटे हैं")
    # Sarvam rejects "audio/webm;codecs=opus": the adapter must send the bare type, auto-detect language
    sent = net.stt_seen[0]
    assert "Content-Type: audio/webm\r\n" in sent and "codecs" not in sent and "unknown" in sent
    # reply audio: synthesized on first GET, cached afterwards
    url = d["speak"]["audio_url"]
    assert url.startswith("http://localhost:8000/v1/audio/") and net.tts_calls == 0
    path = url.replace("http://localhost:8000", "")
    a = api.get(path)
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav" and a.content == WAV
    api.get(path)
    assert net.tts_calls == 1
    assert d["messages"][1]["audio_url"] == url
    stt_event = events(api, cid, "STT")[0]["payload"]
    assert "transcript" not in json.dumps(stt_event) and net.transcript not in json.dumps(stt_event)


def test_marathi_speech_gets_marathi_reply(api, net):
    net.transcript, net.stt_lang = "माझे पैसे कापले पण मिळाले नाहीत", "mr-IN"
    d = say_audio(api, open_case(api, "txn_s2_citymobiles")).json()
    assert d["lang"] == "mr" and d["speak"]["text"].startswith("हो, तुमच्या खात्यातून 1,499 रुपये कापले गेले आहेत")


def test_no_speech(api, net):
    net.transcript = "  "
    r = say_audio(api, open_case(api, "txn_f3_gupta"))
    assert r.status_code == 422 and r.json()["detail"] == "no_speech"


def test_stt_failure_is_reported(api, net):
    net.stt_status = 500
    r = say_audio(api, open_case(api, "txn_f3_gupta"))
    assert r.status_code == 502 and r.json()["detail"] == "stt_failed"


def test_unusable_clip_is_no_speech_not_an_outage(api, net):
    net.stt_status = 400  # Sarvam: "Audio duration is 0, please check the audio."
    r = say_audio(api, open_case(api, "txn_f3_gupta"))
    assert r.status_code == 422 and r.json()["detail"] == "no_speech"


def test_audio_token_must_exist(api):
    assert api.get("/v1/audio/" + "0" * 32).status_code == 404
    assert api.get("/v1/audio/../../etc").status_code == 404


def test_idempotent_audio_turn_does_not_call_stt_twice(api, net):
    cid = open_case(api, "txn_f3_gupta")
    h = {"Idempotency-Key": "voice-1"}
    a = say_audio(api, cid, headers=h)
    b = say_audio(api, cid, headers=h)
    assert a.json() == b.json() and len(net.stt_seen) == 1


# ------------------------------------------------------------------ 1. intent

def test_llm_intent_only_when_keywords_miss(api, net):
    cid = open_case(api, "txn_f3_gupta")
    say(api, cid, "paise kat gaye kya")  # keywords match: no LLM call
    assert net.llm_calls == []
    d = say(api, cid, "could you look into this one for me")
    assert len(net.llm_calls) == 1 and d["intent"] == "why"
    ev = events(api, cid, "LLM_INTENT")[0]["payload"]
    assert ev["intent"] == "why" and "look into" not in json.dumps(ev)  # no user text in the audit


def test_llm_intent_low_confidence_falls_back(api, net):
    net.intent = {"intent": "talk_to_human", "language": "en", "confidence": 0.3}
    d = say(api, open_case(api, "txn_f3_gupta"), "hmm okay alright then")
    assert events(api, d["case_id"], "LLM_INTENT")  # the LLM was asked, and ignored
    assert d["intent"] == "status_check" and d["case"]["state"] == "WAITING"


def test_llm_garbage_falls_back(api, net):
    net.intent = "I think the user wants help!"
    d = say(api, open_case(api, "txn_f3_gupta"), "could you look into this one for me")
    assert d["intent"] == "status_check"
    assert events(api, d["case_id"], "LLM_INTENT")[0]["payload"]["ok"] is False


def test_reasoning_truncation_is_reported(vsettings):
    # deepseek-flash spends max_tokens on hidden reasoning; content can come back empty
    def handler(_req):
        return httpx.Response(200, json={"choices": [{"finish_reason": "length",
                                                      "message": {"content": "", "reasoning_content": "hmm"}}]})
    out, meta = LLMClient(vsettings, httpx.MockTransport(handler)).complete_json("s", "u", llm_tasks.IntentOut)
    assert out is None and not meta.ok and "LLM_MAX_TOKENS" in meta.error


def test_llm_flags_off_topic_without_keywords(api, net):
    net.intent = {"intent": "off_topic", "language": "en", "confidence": 0.95}
    d = say(api, open_case(api, "txn_s2_citymobiles"), "who won the election in 1998")
    assert d["intent"] == "off_topic" and d["speak"]["text"].startswith("Please stay relevant to this transaction")


def test_llm_cannot_confirm_a_retry_that_is_not_on_offer(api, net):
    net.intent = {"intent": "confirm_retry", "language": "en", "confidence": 0.99}
    d = say(api, open_case(api, "txn_s2_citymobiles"), "could you look into this one for me")
    assert d["intent"] == "status_check" and d["actions"] == []


# ------------------------------------------------------------------ 2. rephrase

def test_rephrase_is_number_checked(api, net, vsettings):
    api.app_state.settings.LLM_REPHRASE_ENABLED = True
    cid = open_case(api, "txn_s2_citymobiles")
    net.rephrase = "Yes, ₹1,500 left your account and will be back by 9 October."  # wrong numbers
    d = say(api, cid, "money got cut?")
    assert d["speak"]["text"].startswith("Yes, ₹1,499 was taken from your account")  # template kept
    assert events(api, cid, "LLM_REPHRASE")[-1]["payload"]["reason"] == "number_check_failed"
    net.rephrase = "Yes, ₹1,499 left your account but did not reach City Mobiles. Please do not pay again. It should come back by 4 October."
    d = say(api, cid, "money got cut?")
    assert d["speak"]["text"] == net.rephrase
    assert events(api, cid, "LLM_REPHRASE")[-1]["payload"]["used"] is True


def test_retry_read_back_is_never_rephrased(api, net):
    api.app_state.settings.LLM_REPHRASE_ENABLED = True
    net.rephrase = "Okay! Sending money now."
    cid = open_case(api, "txn_s1_sharma")
    d = api.post(f"/v1/cases/{cid}/retry/confirm").json()
    assert d["ok"] and d["speak"]["text"].startswith("Paying ₹350 to Sharma Medicals")


# ------------------------------------------------------------------ 3. AMBIGUOUS classification

def _ambiguous_payment(api):
    # NPCI status unavailable -> the rules return AMBIGUOUS
    r = api.post("/v1/events/transactions", json={
        "payee_vpa": "newshop@ybl", "payee_name": "New Shop", "amount_paise": 9900, "status": "FAILED",
        "mock_evidence": {"ledger": {"state": "NO_DEBIT"}, "merchant": {"credited": False}}})
    assert r.status_code == 201, r.text
    return r.json()["case"]


def test_llm_classifies_ambiguous_case(api, net):
    case = _ambiguous_payment(api)
    assert (case["class"], case["decision"], case["rule"]) == ("F3_PENDING", "WAIT", "4")
    ev = events(api, case["id"], "LLM_CLASSIFIED")[0]["payload"]
    assert ev["result"]["source"] == "LLM" and ev["ok"]


def test_low_confidence_llm_class_escalates(api, net):
    net.klass = {"case_class": "F1_DECLINED_PRE_DEBIT", "confidence": 0.4, "reasons": ["guess"]}
    case = _ambiguous_payment(api)
    assert (case["decision"], case["rule"]) == ("ESCALATE", "8")


def test_llm_class_cannot_unlock_a_retry_without_evidence(api, net):
    # Even a confident F1 from the LLM cannot pass the gate: NPCI final FAILED is not proven.
    net.klass = {"case_class": "F1_DECLINED_PRE_DEBIT", "confidence": 0.95, "reasons": ["looks declined"]}
    case = _ambiguous_payment(api)
    assert case["decision"] == "ESCALATE" and case["state"] == "ESCALATED"


def test_llm_choosing_ambiguous_is_rejected(api, net):
    net.klass = {"case_class": "AMBIGUOUS", "confidence": 0.9, "reasons": []}
    case = _ambiguous_payment(api)
    assert case["decision"] == "ESCALATE"
    assert events(api, case["id"], "LLM_CLASSIFIED")[0]["payload"]["ok"] is False


# ------------------------------------------------------------------ 4. case-file summary

def test_case_summary_job_for_escalation(api, net):
    cid = open_case(api, "txn_f3_gupta")
    say(api, cid, "I want to talk to a human")
    with api.app_state.SessionLocal() as db:
        done = run_due_jobs(db, api.app_state.settings)
    assert any(j["kind"] == "CASE_SUMMARY" and j["status"] == "DONE" for j in done)
    item = next(c for c in api.get("/v1/review/queue").json()["cases"] if c["id"] == cid)
    assert item["case_file"]["llm_summary"] == net.summary


def test_case_summary_with_invented_numbers_is_rejected(api, net):
    net.summary = "Customer lost ₹98,765 across 4 payments."
    cid = open_case(api, "txn_f3_gupta")
    say(api, cid, "I want to talk to a human")
    with api.app_state.SessionLocal() as db:
        done = run_due_jobs(db, api.app_state.settings)
    job = next(j for j in done if j["kind"] == "CASE_SUMMARY")
    assert job["status"] == "QUEUED" and "numbers not in the case file" in job["error"]  # retried later
    item = next(c for c in api.get("/v1/review/queue").json()["cases"] if c["id"] == cid)
    assert "llm_summary" not in item["case_file"]


def test_health_reports_providers(api):
    h = api.get("/healthz").json()
    assert h["llm"] and h["stt"] and h["tts"]


def test_delete_my_data_removes_reply_audio(api, vsettings):
    from pathlib import Path

    cid = open_case(api, "txn_f3_gupta")
    url = say(api, cid, "why?")["speak"]["audio_url"]
    api.get(url.replace("http://localhost:8000", ""))
    files = list((Path(vsettings.MEDIA_DIR) / "audio").glob("*.wav"))
    assert files
    api.delete("/v1/me/data")
    assert not any(f.exists() for f in files)
