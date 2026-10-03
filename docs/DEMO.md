# Demo runbook (spec §17)

Every beat of the spec §17 script, as exact clicks and words. Each beat is covered by an automated test (named in the last column), so a green `pytest` run means the script works.

## Setup (5 minutes before)

```powershell
cd backend
.venv\Scripts\python scripts\reset_db.py        # fresh demo data; problem payments are "today"
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

1. Open **http://localhost:8000/console.html** on the laptop and keep it on the **Live** tab. This is the two-screen layout from §17: the app in a phone frame on the left, the agent activity panel on the right. The panel follows whatever case the agent touched last.
2. Allow the microphone when Chrome asks. The mic works inside the phone frame on `localhost`. For a real phone, use an HTTPS tunnel and set `PUBLIC_BASE_URL`.
3. Check the server is up: `/healthz` should show `stt`, `tts` and `llm` as `true`. If voice is off, the chat still works by typing (fallback).
4. Optional: open **Numbers** once, so the evaluation is loaded.

## 1. Hook (30 s): before / after

Show the screenshots of our real Paytm test (spec 1.0): the old ₹10 chat reopened, no way to start a new one, and the bot answering about the wrong payment. Then say: "Here's the same moment with our teammate."

In the phone, the **Anil Kumar ₹1** payment (11:19 am, "Bad Network") is the same failure. Tap it, then the mic, and say **"issue regarding last payment"**. The answer is about the ₹1 payment, not the ₹10 one. *(Test: `test_new_failure_gets_its_own_session`; the evaluation's right-payment check, 50/50.)*

## 1b. The main flow: the payment fails and the agent speaks first

Your mentor's point: users shouldn't have to discover a button. So now the agent comes to them.

| Do | Say / tap | You'll see |
|---|---|---|
| Phone: tap **Scan & Pay** on Home | | The viewfinder; a demo merchant QR (e.g. Kaveri Restaurant) is "scanned" |
| Enter an amount (e.g. 640), then **Proceed to pay**, then any PIN | | "Paying…", then **Payment failed**: "Amount debited but not credited to the merchant" |
| Wait about 2 s | | The chat opens and **the agent speaks first**: "Your ₹640 payment to Kaveri Restaurant didn't go through. Would you like me to check what happened to your money?". The voice bar shows **Listening…** |
| Answer | "haan, kya hua?" / "yes" / "paise kat gaye kya?" | The S2-style answer: debited, don't pay again, comes back by the date. The conversation continues hands-free, as before. "No thanks" ends it. |

The way it fails is set by `DEMO_SCAN_PAY_FAILURE` in `backend/.env`: `debited` (default), `declined`, `bank_down`, `pending` or `off`. Restart the server after changing it. Skip time +1 day twice and this payment gets the automatic dispute too.

*(Tests: `test_scan_pay_fails_on_purpose_and_case_is_prepared`, `test_agent_offers_help_first_then_answers`, `test_yes_to_the_offer_never_confirms_a_retry`.)*

## 2. S1: safe retry (Sharma Medicals ₹350)

| Do | Say / tap | You'll see |
|---|---|---|
| Tap **Sharma Medicals**, then the mic | "Did my money get cut?" (or "mera paisa kata kya?") | The live transcript, then the chat: "No… no money was taken… Would you like to pay again?" The panel shows evidence → F1 → rule 7 → re-check passed. |
| Answer | "Yes" (or tap **Pay ₹350 again**) | The read-back, then the retry gate at 10/10 in the panel, then the pre-filled pay screen |
| Enter any 4–6 digit PIN | | Payment successful; the case is closed |

*(Test: `test_s1_safe_retry`.)*

**Optional, late debit.** Before saying "yes", click **Late debit on Sharma Medicals** under the phone. Then say "yes". The panel shows **"Live re-check: the world changed · action cancelled"**, the class becomes F4, and the agent says to wait instead of opening the pay screen. *(Test: `test_demo_late_debit_is_caught_by_the_live_recheck`.)*

## 3. S2: debited, not credited (City Mobiles ₹1,499)

| Do | Say / tap | You'll see |
|---|---|---|
| Tap **City Mobiles**, then the mic | "paise kat gaye par mila nahi" (Hindi) | A Hindi reply: ₹1,499 was debited, don't pay again, it comes back by the T+1 date |
| Follow up | "agar wapas nahi aaya to?" | It explains the automatic complaint and compensation |
| Click **Skip time +1 day** twice | | The panel shows the background job → re-check → **dispute raised (UDIR ref)** → **compensation flagged** |
| Phone: back to history | | City Mobiles has a red badge; reopen it and the new message is at the bottom of its chat |

*(Tests: `test_s2_hinglish_then_deadline_dispute`, `test_scheduler.py`.)*

## 4. S3: suspicious / conflict (Patel Electronics ₹2,000)

| Do | Say / tap | You'll see |
|---|---|---|
| Tap **Patel Electronics**, then the mic | "paise kat gaye par mila nahi" | The agent refuses to act: the records don't match, it has passed the case to an expert, and says not to pay again |
| Console: **Review queue** | | The case file: evidence from each source, 3 conflicts in red, rule trace, recommended actions, and what the agent told the user |
| Click **Approve** (or **Ask the user for more info**) | | The phone chat gets the specialist's message in the user's language; notes stay internal |

*(Tests: `test_s3_suspicious_escalates_with_case_file`, `test_review_request_info_keeps_case_escalated_and_asks_user`.)*

## 5. Numbers (console **Numbers** tab)

Say: "These are simulator numbers on 3,000 generated cases; the mix is our assumption."

- **False retries:** B0 (Paytm record only) offers 670 unsafe retries (27.8%). The full system offers **0**.
- **Wrong closes / disputes:** 0.
- **The live re-check cancelled 95 actions**, every one of which would have been wrong.
- **B2 (with the LLM)** raises diagnosis accuracy from 93.1% to 96.5%. The evaluation also caught a bug where the LLM could trigger a dispute; we fixed it, and now the LLM can only make the agent wait or escalate.
- **Failures we report:** 53 needless escalations (see `docs/EVALUATION.md`).

## 6. Close

Say: "UPI Help needs you to describe the problem. Our agent lives inside Paytm, already knows what happened when you open it, tells you in your own language, retries safely when it's safe, and chases the bank in the background when it isn't. **The AI does the work; rules decide what it's allowed to do.**"

Say plainly what is mocked and what is real:
- **Mocked:** Paytm records, NPCI, bank, merchant, UDIR, and the money.
- **Real:** Sarvam speech-to-text and text-to-speech, the DeepSeek LLM, and the decision engine.

## Optional: bank outage

Click **Bank outage: fail a payment** a few times. Each click fails a new payment with the bank down, and each is prepared in the background as F6 → WAIT. Tap the mic on any of them: "your bank is having trouble, your money is safe, don't pay again". The **Review queue** count does not go up: no human was needed. *(Test: `test_demo_bank_outage_is_answered_without_a_human`.)*

## Fallbacks

- **Voice fails:** type in the chat. The same answers come back.
- **The app breaks:** run `reset_db.py` (about 2 s), or play the recorded clip.
- **Repeat a scenario:** run `reset_db.py`. All times are relative, so the problem payments are always "today".
