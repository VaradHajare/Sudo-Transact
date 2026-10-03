"""End-to-end over HTTP for the demo scenarios S1 / S2 / S3 and the five key calls."""
import pytest


@pytest.fixture
def api(client):
    tok = client.post("/v1/session", json={"user_id": "u_demo"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {tok}"
    return client


def open_case(api, txn_id):
    r = api.post("/v1/cases/open", json={"txn_id": txn_id})
    assert r.status_code == 200, r.text
    return r.json()


def say(api, case_id, text=None, chip=None, **kw):
    body = {"case_id": case_id, **({"text": text} if text else {}), **({"chip_id": chip} if chip else {})}
    r = api.post("/v1/voice/turn", json=body, **kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_required(client):
    assert client.get("/v1/transactions").status_code == 401
    assert client.get("/v1/transactions", headers={"Authorization": "Bearer junk.sig"}).status_code == 401


def test_history_shape_and_badges(api):
    txns = api.get("/v1/transactions").json()["transactions"]
    s2 = next(t for t in txns if t["id"] == "txn_s2_citymobiles")
    for k in ("id", "payeeName", "payeeVpa", "amountPaise", "status", "debited", "timestamp", "note",
              "direction", "category", "railLabel"):
        assert k in s2
    assert s2["amountPaise"] == 149900 and s2["case"]["situation"] == "DEBIT_WAIT"
    ramesh = next(t for t in txns if t["id"] == "txn_10_ramesh")
    assert ramesh["case"]["hasUpdate"] is True  # reversal landed in the background
    assert next(t for t in txns if t["id"] == "txn_rahul_in")["case"] is None


def test_s1_safe_retry(api):
    o = open_case(api, "txn_s1_sharma")
    assert o["prepared_in_background"] and o["case"]["decision"] == "OFFER_RETRY"
    cid = o["case"]["id"]
    r = say(api, cid, "Did my money get cut?")
    assert r["speak"]["text"].startswith("No. Your ₹350 payment to Sharma Medicals didn't go through")
    assert r["chips"][0] == {"id": "retry", "label": "Pay ₹350 again"}
    assert r["speak"]["audio_url"] is None  # TTS off

    c = api.post(f"/v1/cases/{cid}/retry/confirm").json()
    assert c["ok"] and c["pay_screen"]["payee_vpa"] == "sharmamedicals@paytm" and c["pay_screen"]["amount_paise"] == 35000
    assert c["speak"]["text"].startswith("Paying ₹350 to Sharma Medicals")

    # a tampered amount is refused
    bad = api.post("/v1/payments", json={"payee_vpa": "sharmamedicals@paytm", "payee_name": "Sharma Medicals",
                                         "amount_paise": 3500000, "pin": "1234", "retry_of_case_id": cid})
    assert bad.status_code == 409
    p = api.post("/v1/payments", json={"payee_vpa": "sharmamedicals@paytm", "payee_name": "Sharma Medicals",
                                       "amount_paise": 35000, "pin": "1234", "retry_of_case_id": cid})
    assert p.status_code == 201 and p.json()["transaction"]["status"] == "SUCCESS"
    assert p.json()["case"]["state"] == "RESOLVED"
    msgs = api.get(f"/v1/cases/{cid}/messages").json()["messages"]
    assert msgs[-1]["kind"] == "update" and "went through" in msgs[-1]["text"]


def test_s1_late_debit_caught_by_recheck(api):
    cid = open_case(api, "txn_s1_sharma")["case"]["id"]
    say(api, cid, "Did my money get cut?")
    api.post("/mock/inject", json={"txn_id": "txn_s1_sharma", "ledger": {"state": "DEBITED"}})
    r = say(api, cid, "yes")
    assert r["actions"] == []  # no pay screen
    assert r["case"]["class"] == "F4_DEBIT_NO_CREDIT" and r["situation"] == "DEBIT_WAIT"
    events = [e["event"] for e in api.get(f"/v1/cases/{cid}/activity").json()["events"]]
    assert "RECHECK_CHANGED" in events


def test_s2_hinglish_then_deadline_dispute(api):
    o = open_case(api, "txn_s2_citymobiles")
    cid = o["case"]["id"]
    expected_by = o["case"]["expected_by"]
    r = say(api, cid, "paise kat gaye par mila nahi")
    assert r["lang"] == "hi" and r["decision"] == "WAIT" and r["situation"] == "DEBIT_WAIT"
    assert r["speak"]["text"].startswith("हाँ, आपके खाते से 1,499 रुपये कटे हैं, लेकिन सिटी मोबाइल्स को नहीं पहुंचे।")
    assert "दोबारा पेमेंट मत कीजिए" in r["speak"]["text"]
    assert r["speak"]["facts"]["expected_by"] == expected_by
    assert {c["id"] for c in r["chips"]} == {"what_if", "why", "talk_to_human"}

    r2 = say(api, cid, "agar nahi aaya to?")
    assert "अपने आप शिकायत दर्ज कर दूँगा" in r2["speak"]["text"]

    # deadline passes -> re-check -> dispute + compensation, user sees it on reopen
    skip = api.post("/mock/clock", json={"advance_days": 2}).json()
    assert any(x["case_id"] == cid and x["kind"] == "SLA_DEADLINE" and x["to"] == "DISPUTED" for x in skip["jobs_run"])
    txns = api.get("/v1/transactions").json()["transactions"]
    assert next(t for t in txns if t["id"] == "txn_s2_citymobiles")["case"]["hasUpdate"] is True
    again = open_case(api, "txn_s2_citymobiles")
    assert again["case"]["id"] == cid  # same session for the same payment
    last = again["messages"][-1]
    assert last["role"] == "agent" and last["kind"] == "update"
    assert last["text"].startswith("आपके 1,499 रुपये समय पर वापस नहीं आए, इसलिए मैंने शिकायत दर्ज कर दी है")
    assert again["case"]["dispute"]["ref"] in last["text"] and again["case"]["compensation"]["amount_paise"] >= 10000
    assert again["case"]["has_unseen_update"] is False


def test_s3_suspicious_escalates_with_case_file(api):
    cid = open_case(api, "txn_s3_patel")["case"]["id"]
    r = say(api, cid, "paise kat gaye par mila nahi")
    assert r["decision"] == "ESCALATE" and r["actions"] == [] and r["chips"] == []
    assert "विशेषज्ञ" in r["speak"]["text"]
    q = api.get("/v1/review/queue").json()["cases"]
    item = next(c for c in q if c["id"] == cid)
    assert item["case_file"]["conflicts"] and item["case_file"]["rule_trace"]
    d = api.post(f"/v1/review/{cid}/decision", json={"decision": "APPROVE", "notes": "bank confirmed no debit"})
    assert d.json()["case"]["state"] == "REVIEWED"
    # the outcome reaches the user's chat (their language), never the reviewer's notes
    reopened = open_case(api, "txn_s3_patel")
    last = reopened["messages"][-1]
    assert last["kind"] == "update" and "विशेषज्ञ" in last["text"] and "bank confirmed" not in last["text"]
    assert reopened["case"]["status_line"] == "Reviewed by a specialist"
    assert say(api, cid, "ab kya hua")["situation"] == "REVIEWED"


def test_review_request_info_keeps_case_escalated_and_asks_user(api):
    cid = open_case(api, "txn_s3_patel")["case"]["id"]
    d = api.post(f"/v1/review/{cid}/decision", json={"decision": "REQUEST_INFO"}).json()
    assert d["case"]["state"] == "ESCALATED"
    msgs = api.get(f"/v1/cases/{cid}/messages").json()["messages"]
    assert "bank statement" in msgs[-1]["text"]


def test_console_feed_case_detail_and_evaluation(api):
    open_case(api, "txn_s2_citymobiles")
    cases = api.get("/v1/review/cases").json()["cases"]
    assert cases[0]["txn_id"] == "txn_s2_citymobiles"  # most recently active first
    detail = api.get(f"/v1/review/cases/{cases[0]['id']}").json()
    assert any(e["event"] == "CASE_OPENED_BY_USER" for e in detail["events"])
    ev = api.get("/v1/review/evaluation")
    assert ev.status_code in (200, 404)
    if ev.status_code == 200:
        assert {"B0", "B1", "B2"} <= set(ev.json()["baselines"])


def test_amount_claim_mismatch_escalates(api):
    cid = open_case(api, "txn_s2_citymobiles")["case"]["id"]
    r = say(api, cid, "mere 5000 rupaye kat gaye")
    assert r["case"]["class"] == "F10_SUSPICIOUS" and r["decision"] == "ESCALATE"


def test_new_failure_gets_its_own_session(api):
    c1 = open_case(api, "txn_1fail_anil")
    assert c1["messages"] == []  # fresh session, bound to the Rs 1 failure
    r = say(api, c1["case"]["id"], "issue regarding last payment")
    assert r["speak"]["text"] == ("No. Your ₹1 payment to Anil Kumar didn't go through, and no money was "
                                  "taken from your account. Would you like to pay again?")

    c10 = open_case(api, "txn_10_ramesh")
    assert c10["case"]["id"] != c1["case"]["id"]
    assert [m["kind"] for m in c10["messages"]] == ["update"]  # its own history only
    assert all("Anil" not in m["text"] for m in c10["messages"])


def test_first_reply_briefs_about_dispute_on_another_case(api):
    api.post("/mock/clock", json={"advance_days": 2})  # S2 dispute raised in the background
    cid = open_case(api, "txn_f3_gupta")["case"]["id"]
    r = say(api, cid, "what happened?")
    assert r["speak"]["text"].endswith("Also: I raised a complaint for your ₹1,499 payment to City Mobiles.")
    assert "Also:" not in say(api, cid, "why?")["speak"]["text"]  # only on the first reply


def test_end_conversation_flag_for_hands_free_mode(api):
    cid = open_case(api, "txn_s2_citymobiles")["case"]["id"]
    r = say(api, cid, "paise kat gaye par mila nahi")
    assert r["end_conversation"] is False and r["chips"]
    r = say(api, cid, "theek hai, dhanyavad")
    assert r["intent"] == "goodbye" and r["end_conversation"] is True and r["chips"] == []
    assert r["speak"]["text"].startswith("आपका स्वागत है")
    assert r["case"]["state"] == "WAITING"  # a goodbye changes nothing about the case

    s1 = open_case(api, "txn_s1_sharma")["case"]["id"]
    say(api, s1, "Did my money get cut?")
    r = say(api, s1, "ok thanks")  # must not open the pay screen
    assert r["actions"] == [] and r["case"]["state"] == "RETRY_OFFERED" and r["end_conversation"]
    r = say(api, s1, "yes")
    assert r["actions"][0]["type"] == "OPEN_PAY_SCREEN" and r["end_conversation"] is True


@pytest.mark.parametrize("text,lang,start", [
    ("Can you give me the code for palindrome?", "en",
     "Please stay relevant to this transaction. I can only help with your ₹350 payment to Sharma Medicals"),
    ("aaj mausam kaisa hai bhai", "hi", "कृपया इसी लेन-देन से जुड़ी बात पूछिए। मैं सिर्फ़ शर्मा मेडिकल्स को किए गए आपके 350 रुपये"),
    ("मला एक विनोद सांगा", "mr", "कृपया याच व्यवहाराशी संबंधित विचारा. मी फक्त शर्मा मेडिकल्स ला केलेल्या तुमच्या 350 रुपयांच्या"),
])
def test_off_topic_is_redirected_in_the_users_language(api, text, lang, start):
    cid = open_case(api, "txn_s1_sharma")["case"]["id"]
    r = say(api, cid, text)
    assert r["intent"] == "off_topic" and r["lang"] == lang
    assert r["speak"]["text"].startswith(start)
    assert r["actions"] == [] and r["case"]["state"] == "RETRY_OFFERED"  # nothing about the case changes
    assert r["chips"]  # the chips steer back to the payment


def test_off_topic_amounts_are_not_claims(api):
    cid = open_case(api, "txn_s2_citymobiles")["case"]["id"]
    r = say(api, cid, "what is 5000 rupees in dollars")
    assert r["intent"] == "off_topic"
    assert r["case"]["class"] == "F4_DEBIT_NO_CREDIT" and r["case"]["state"] == "WAITING"  # not escalated as F10


def test_talk_to_human(api):
    cid = open_case(api, "txn_f3_gupta")["case"]["id"]
    r = say(api, cid, chip="talk_to_human")
    assert r["case"]["state"] == "ESCALATED" and r["messages"][0]["text"] == "Talk to a human"
    q = api.get("/v1/review/queue").json()["cases"]
    assert next(c for c in q if c["id"] == cid)["escalation_reason"] == "USER_REQUESTED"


def test_manual_dispute_only_when_rules_allow(api):
    cid = open_case(api, "txn_s1_sharma")["case"]["id"]
    r = api.post(f"/v1/cases/{cid}/dispute")
    assert r.status_code == 409 and r.json()["rule"] == "7"


def test_idempotent_turn_replay(api):
    cid = open_case(api, "txn_f3_gupta")["case"]["id"]
    h = {"Idempotency-Key": "k-1"}
    a = api.post("/v1/voice/turn", json={"case_id": cid, "text": "why?"}, headers=h)
    b = api.post("/v1/voice/turn", json={"case_id": cid, "text": "why?"}, headers=h)
    assert a.json() == b.json() and b.headers.get("Idempotent-Replay") == "true"
    assert len(api.get(f"/v1/cases/{cid}/messages").json()["messages"]) == 2
    c = api.post("/v1/voice/turn", json={"case_id": cid, "text": "different"}, headers=h)
    assert c.status_code == 422


def test_audio_needs_stt(api):
    cid = open_case(api, "txn_f3_gupta")["case"]["id"]
    r = api.post("/v1/voice/turn", data={"case_id": cid}, files={"audio": ("a.webm", b"xx", "audio/webm")})
    assert r.status_code == 422 and "stt_disabled" in r.text


def test_event_ingest_prepares_case(api):
    r = api.post("/v1/events/transactions", json={
        "payee_vpa": "newshop@ybl", "payee_name": "New Shop", "amount_paise": 9900, "status": "FAILED",
        "failure_code": "BANK_UNAVAILABLE",
        "mock_evidence": {"npci": {"status": "FAILED", "reason_code": "BANK_UNAVAILABLE"},
                          "ledger": {"state": "NO_DEBIT"}, "merchant": {"credited": False}}})
    assert r.status_code == 201
    assert r.json()["case"]["class"] == "F6_BANK_DOWNTIME" and r.json()["case"]["decision"] == "WAIT"


def test_cannot_open_someone_elses_payment(api):
    assert api.post("/v1/cases/open", json={"txn_id": "nope"}).status_code == 404


def test_delete_my_data(api):
    cid = open_case(api, "txn_f3_gupta")["case"]["id"]
    say(api, cid, "why?")
    r = api.delete("/v1/me/data").json()
    assert r["deleted_messages"] >= 2
    assert api.get(f"/v1/cases/{cid}/messages").json()["messages"] == []


# ---- spec 17 optional demo moments
def test_demo_bank_outage_is_answered_without_a_human(api):
    r = api.post("/mock/scenario", json={"name": "bank_outage"}).json()
    assert (r["class"], r["decision"]) == ("F6_BANK_DOWNTIME", "WAIT")
    opened = open_case(api, r["txn_id"])
    reply = say(api, opened["case"]["id"], "mera paisa kaha gaya")
    assert reply["decision"] == "WAIT" and reply["situation"] == "BANK_DOWN"
    assert all(c["id"] != r["case_id"] for c in api.get("/v1/review/queue").json()["cases"])


def test_demo_late_debit_is_caught_by_the_live_recheck(api):
    cid = open_case(api, "txn_s1_sharma")["case"]["id"]
    assert say(api, cid, "did my money get cut?")["decision"] == "OFFER_RETRY"
    api.post("/mock/scenario", json={"name": "late_debit"})
    r = say(api, cid, "yes")
    assert not any(a["type"] == "OPEN_PAY_SCREEN" for a in r["actions"])
    assert r["case"]["class"] == "F4_DEBIT_NO_CREDIT" and r["decision"] == "WAIT"
    events = [e["event"] for e in api.get(f"/v1/review/cases/{cid}").json()["events"]]
    assert "RECHECK_CHANGED" in events


# ---- Scan & Pay fails in front of the user; the agent offers help first (mentor feedback)
def scan_and_pay(api, amount=25000):
    qr = api.post("/v1/scan").json()
    r = api.post("/v1/payments", json={**qr, "amount_paise": amount, "pin": "1234", "origin": "scan"})
    assert r.status_code == 201, r.text
    return r.json()


def test_scan_pay_fails_on_purpose_and_case_is_prepared(api):
    out = scan_and_pay(api)
    assert out["transaction"]["status"] == "FAILED" and out["transaction"]["debited"] is True
    assert (out["case"]["class"], out["case"]["decision"]) == ("F4_DEBIT_NO_CREDIT", "WAIT")


def test_failed_payment_opens_with_three_agent_investigation_in_ui_language(api):
    txn = scan_and_pay(api, 64000)["transaction"]
    r = api.post("/v1/cases/open", json={"txn_id": txn["id"], "investigate": True},
                 headers={"X-UI-Lang": "hi"}).json()
    inv = r["investigation"]
    assert [a["id"] for a in inv["agents"]] == ["bank", "rules", "followup"]
    assert inv["intro"]["text"].startswith("कावेरी रेस्टोरेंट को आपका 640 रुपये का पेमेंट असफल रहा")
    bank = " ".join(next(a for a in inv["agents"] if a["id"] == "bank")["lines"])
    assert "NPCI के अनुसार: असफल" in bank and "640 रुपये कटे" in bank and "कावेरी रेस्टोरेंट को पैसा नहीं मिला" in bank
    rules = " ".join(next(a for a in inv["agents"] if a["id"] == "rules")["lines"])
    assert "(F4)" in rules and "नियम 5" in rules and "कुछ नहीं बदला" in rules  # diagnosis, rule, live re-check
    assert inv["conclusion"]["text"].startswith("जाँच पूरी हुई। हाँ, आपके खाते से 640 रुपये कटे")
    assert [c["id"] for c in inv["conclusion"]["chips"]] == ["what_if", "why", "talk_to_human"]
    # labels follow the UI language too
    assert r["case"]["card"]["statusLine"].startswith("पैसा") and r["transaction"]["failureReason"].startswith("पैसा कटा")
    assert r["transaction"]["payeeName"] == r["case"]["card"]["payeeName"] == "कावेरी रेस्टोरेंट"
    # once per case; the chat history keeps both messages, the intro carrying the agents
    again = api.post("/v1/cases/open", json={"txn_id": txn["id"], "investigate": True}).json()
    assert again["investigation"] is None and len(again["messages"]) == 2
    assert again["messages"][0]["actions"][0]["type"] == "INVESTIGATION"


def test_investigation_reports_a_live_change(api):
    txn = scan_and_pay(api)["transaction"]
    api.post("/mock/inject", json={"txn_id": txn["id"], "ledger": {"state": "REVERSED"}})
    inv = api.post("/v1/cases/open", json={"txn_id": txn["id"], "investigate": True}).json()["investigation"]
    rules = next(a for a in inv["agents"] if a["id"] == "rules")
    assert rules["tone"] == "warn" and "bank changed" in " ".join(rules["lines"])
    assert "came back" in inv["conclusion"]["text"]


def test_ui_language_decides_the_reply_language(api):
    cid = open_case(api, "txn_s2_citymobiles")["case"]["id"]
    # Hinglish question, Marathi UI: the answer is in Marathi
    r = api.post("/v1/voice/turn", json={"case_id": cid, "text": "paise kat gaye par mila nahi"},
                 headers={"X-UI-Lang": "mr"}).json()
    assert r["lang"] == "mr" and "रुपये" in r["speak"]["text"]
    # English UI, Hindi question: English answer
    r = api.post("/v1/voice/turn", json={"case_id": cid, "text": "मेरे पैसे कटे क्या?"},
                 headers={"X-UI-Lang": "en"}).json()
    assert r["lang"] == "en" and r["speak"]["text"].startswith("Yes, ₹1,499 was taken")
    # no header: the old behaviour (detected language)
    r = say(api, cid, "paise kat gaye par mila nahi")
    assert r["lang"] == "hi"


def test_scan_pay_can_be_switched_off(client):
    client.app.state.settings.DEMO_SCAN_PAY_FAILURE = "off"
    tok = client.post("/v1/session", json={"user_id": "u_demo"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    qr = client.post("/v1/scan", headers=h).json()
    r = client.post("/v1/payments", json={**qr, "amount_paise": 5000, "pin": "1234", "origin": "scan"}, headers=h)
    assert r.json()["transaction"]["status"] == "SUCCESS"


def test_payee_names_follow_the_ui_language(api):
    hi = {"X-UI-Lang": "hi"}
    txns = {t["id"]: t for t in api.get("/v1/transactions", headers=hi).json()["transactions"]}
    assert txns["txn_s1_sharma"]["payeeName"] == "शर्मा मेडिकल्स"
    assert api.get("/v1/transactions/txn_s2_citymobiles", headers={"X-UI-Lang": "mr"}).json()["payeeName"] == "सिटी मोबाईल्स"
    assert api.get("/v1/transactions/txn_s2_citymobiles").json()["payeeName"] == "City Mobiles"  # English UI
    qr = api.post("/v1/scan", headers=hi).json()
    assert qr["payee_name"] == "Kaveri Restaurant" and qr["payee_display"] == "कावेरी रेस्टोरेंट"


def test_unknown_payee_words_keep_the_original_name():
    from app.conversation.names import local_name
    assert local_name("Kaveri Restaurant", "mr") == "कावेरी रेस्टॉरंट"
    assert local_name("Zorba Foods", "hi") == "Zorba Foods"  # never half-translated or guessed
    assert local_name("Kaveri Restaurant", "en") == "Kaveri Restaurant"


# ---- "talk to a human" rings the support line (HUMAN_SUPPORT_PHONE)
def test_talk_to_human_rings_the_support_line(api):
    api.app.state.settings.HUMAN_SUPPORT_PHONE = "+911234567890"
    cid = open_case(api, "txn_s2_citymobiles")["case"]["id"]
    r = say(api, cid, chip="talk_to_human")
    assert r["actions"] == [{"type": "CALL_HUMAN", "phone": "+911234567890"}]
    assert r["speak"]["text"].startswith("I'm connecting you to a support specialist")
    assert r["end_conversation"] is True and r["chips"] == []
    assert r["case"]["state"] == "ESCALATED"  # the reviewer still gets the case file
    # asking again (already escalated) still rings, in the user's language
    r = api.post("/v1/voice/turn", json={"case_id": cid, "text": "kisi insaan se baat karao"},
                 headers={"X-UI-Lang": "hi"}).json()
    assert r["actions"][0]["type"] == "CALL_HUMAN" and r["speak"]["text"].startswith("मैं अभी आपको")
    assert "1234567890" not in r["speak"]["text"]  # the number is shown, never spoken


def test_talk_to_human_without_a_support_line_only_escalates(api):
    cid = open_case(api, "txn_s2_citymobiles")["case"]["id"]
    r = say(api, cid, chip="talk_to_human")
    assert r["actions"] == [] and r["case"]["state"] == "ESCALATED"


def test_support_phone_must_be_a_full_number():
    import pytest
    from pydantic import ValidationError
    from app.config import Settings
    assert Settings(_env_file=None, HUMAN_SUPPORT_PHONE="+91 98765-43210").HUMAN_SUPPORT_PHONE == "+919876543210"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, HUMAN_SUPPORT_PHONE="9876543210")
