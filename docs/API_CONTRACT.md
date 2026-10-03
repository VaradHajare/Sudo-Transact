# API contract (v1)

Backend for the AI Resolve feature. Consumers: the web prototype in `web/` today, a Kotlin app later. Nothing here is web-specific.

- **Base URL:** `http://localhost:8000`. The web UI is served from the same origin, so no CORS is needed.
- **Format:** JSON, UTF-8. Money is always **integer paise** (`amountPaise`, `amount_paise`). Timestamps are ISO 8601 in IST (`+05:30`). Dates such as `expected_by` are `YYYY-MM-DD`.
- **Auth:** `Authorization: Bearer <token>` on every `/v1` call except `POST /v1/session`.
- **Idempotency:** send `Idempotency-Key: <uuid>` on mutating calls. A repeat with the same key returns the stored response with the header `Idempotent-Replay: true`. Reusing a key with a different body returns `422`.
- **Errors:** `{"detail": "..."}` with `401` (no or bad token), `404` (not found or not yours), `409` (the rules don't allow it), or `422` (bad input).
- **Field casing:** transactions use camelCase (the UI's shape). Cases and turns use snake_case. The `card` object is camelCase so it can be rendered like a transaction.
- **Mocked:** all payment systems (Paytm records, NPCI, bank, merchant, UDIR).
- **Real providers (when switched on in `backend/.env`):** Sarvam speech-to-text and text-to-speech, and the LLM (DeepSeek). `GET /healthz` reports which are on (`stt`, `tts`, `llm`). When `tts` is off, `audio_url` is `null`; when `stt` is off, send text. The app never holds a provider key.
- **Background work:** a scheduler raises disputes, grows compensation and closes cases on late refunds even when the app is closed. The client learns about it from `case.hasUpdate` in history and a `kind: "update"` message in that case's chat. Nothing is pushed.

**The rule for clients:** never decide anything from the transaction's own fields. In particular, `debited` is only the Paytm record's view, so it must not decide whether a retry is safe. Show `case.status_line`, `speak.text`, `chips` and `actions` from the backend. A retry can only happen through the `OPEN_PAY_SCREEN` action.

## The five key calls

| # | Call | When |
|---|---|---|
| 1 | `GET /v1/transactions` | Payment history (with case badges) |
| 2 | `POST /v1/cases/open` | User taps the mic on a payment: returns the prepared case and chat history |
| 3 | `POST /v1/voice/turn` | Every message the user sends (text or chip) |
| 4 | `POST /v1/cases/{id}/retry/confirm` | User taps "Pay ₹X again" |
| 5 | `GET /v1/cases/{id}/messages` | Reload the chat |

Getting a token first (demo only, no password):

```http
POST /v1/session
{"user_id": "u_demo"}
```
```json
{"token": "eyJ1aWQiOi…", "expires_at": 1791100866,
 "user": {"id": "u_demo", "name": "Demo User", "language": "en"}}
```

---

### 1. `GET /v1/transactions`: payment history

Newest first. `case` is `null` when the payment has no case (successful or incoming payments). `case.hasUpdate` is the history badge.

```json
{
  "transactions": [
    {
      "id": "txn_s2_citymobiles",
      "payeeName": "City Mobiles",
      "payeeVpa": "citymobiles@okicici",
      "amountPaise": 149900,
      "status": "FAILED",
      "debited": true,
      "timestamp": "2026-10-03T11:31:06+05:30",
      "note": "Phone cover + charger",
      "direction": "OUT",
      "category": "Electronics",
      "railLabel": "UPI · State Bank of India ••4821",
      "upiRef": "627401221499",
      "failureReason": "Amount debited but not credited to the beneficiary",
      "case": {
        "id": "c_7ce63426",
        "state": "WAITING",
        "situation": "DEBIT_WAIT",
        "hasUpdate": false,
        "statusLine": "Money should return by 4 October"
      }
    },
    {
      "id": "txn_swiggy", "payeeName": "Swiggy", "payeeVpa": "swiggy@icici", "amountPaise": 38900,
      "status": "SUCCESS", "debited": true, "timestamp": "2026-10-02T08:31:06+05:30", "note": "Dinner",
      "direction": "OUT", "category": "Food", "railLabel": "UPI · State Bank of India ••4821",
      "upiRef": "627400811389", "failureReason": null, "case": null
    }
  ]
}
```

`GET /v1/transactions/{id}` returns a single object of the same shape.

- `status`: `SUCCESS | FAILED | PENDING`. `direction`: `OUT | IN`. For `IN`, `payee*` holds the sender.
- Show the mic button when `direction == "OUT"` and `status` is `FAILED` or `PENDING`.

---

### 2. `POST /v1/cases/open`: user tapped the mic

The case is bound to the payment on screen. There is **one case (one chat session) per payment**; reopening returns the same case and its history. If the case hasn't been prepared yet, it is assembled on demand, so show the "thinking" dots while you wait. Opening also clears the history badge.

```http
POST /v1/cases/open
{"txn_id": "txn_s2_citymobiles"}
```
```json
{
  "case": {
    "id": "c_7ce63426",
    "txn_id": "txn_s2_citymobiles",
    "state": "WAITING",
    "class": "F4_DEBIT_NO_CREDIT",
    "decision": "WAIT",
    "rule": "5",
    "situation": "DEBIT_WAIT",
    "language": "en",
    "has_unseen_update": false,
    "status_line": "Money should return by 4 October",
    "next_action": "Wait for the automatic refund",
    "expected_by": "2026-10-04",
    "deadline": "2026-10-04T23:59:59+05:30",
    "dispute": null,
    "compensation": null,
    "conflicts": [],
    "card": {
      "payeeName": "City Mobiles", "payeeVpa": "citymobiles@okicici", "amountPaise": 149900,
      "status": "FAILED", "timestamp": "2026-10-03T11:31:06+05:30",
      "statusLine": "Money should return by 4 October",
      "nextAction": "Wait for the automatic refund", "expectedBy": "2026-10-04"
    },
    "created_at": "2026-10-03T13:31:06+05:30",
    "updated_at": "2026-10-03T13:31:06+05:30"
  },
  "transaction": { "...": "same shape as in /v1/transactions" },
  "messages": [],
  "briefing": [],
  "prepared_in_background": true
}
```

- `card` is the pinned case card at the top of the chat.
- `messages` is the saved history. When it's empty, start listening right away (spec 4.2). The agent never speaks first.
- `briefing` lists urgent updates on the user's **other** cases (for example a dispute raised there). The backend already appends them to the first reply, so the client doesn't need to show this list.

`state` values: `NEW, WAITING, RETRY_OFFERED, RETRY_CONFIRMED, DISPUTED, CLOSED, RESOLVED, ESCALATED, REVIEWED`.
`situation` values: `RETRY_OFFER, PRE_DEBIT_WAIT, PENDING, BANK_DOWN, DEBIT_WAIT, DISPUTED, DUPLICATE_DISPUTED, REVERSED, SUCCEEDED, ESCALATED, ESCALATED_USER, RESOLVED_BY_RETRY`.

---

### 3. `POST /v1/voice/turn`: one turn

Send what the user said (text, or the final transcript) **or** the id of a chip they tapped.

```http
POST /v1/voice/turn
Idempotency-Key: 6f1c…
{"case_id": "c_7ce63426", "text": "paise kat gaye par mila nahi"}
```

Optional fields:
- `"lang": "en" | "hi" | "mr"`: a hint. The backend detects the language from the text (romanized Hindi and Marathi included) and replies in it.
- `"chip_id"`: send this instead of `text` when the user taps a chip.

**Audio (voice turn):** `multipart/form-data` with `case_id`, an `audio` file and an optional `lang` hint. Any browser or phone format works (webm/opus, ogg, m4a/mp4, wav, mp3), up to 10 MB. The backend calls Sarvam STT with automatic language detection, then handles the transcript like text. The response adds:

```json
"input": "voice",
"user_text": "मेरे पैसे कट गए लेकिन दुकान वाले को नहीं मिले।",
"stt": {"language_code": "hi-IN", "language_probability": 0.967, "latency_ms": 869}
```

| Status | `detail` | Client should |
|---|---|---|
| 422 | `stt_disabled` | Hide the mic and use text |
| 422 | `no_speech` | "I didn't catch that", then listen again. This is also returned when Sarvam rejects an empty or too-short clip ("Audio duration is 0"). |
| 413 | `audio too large` | Record a shorter clip |
| 502 | `stt_failed` | Fall back to typing |

```json
{
  "case_id": "c_7ce63426",
  "decision": "WAIT",
  "rule": "5",
  "situation": "DEBIT_WAIT",
  "intent": "status_check",
  "lang": "hi",
  "user_text": "paise kat gaye par mila nahi",
  "speak": {
    "lang": "hi",
    "text": "हाँ, आपके खाते से 1,499 रुपये कटे हैं, लेकिन City Mobiles को नहीं पहुंचे। दोबारा पेमेंट मत कीजिए। यह पैसा 4 अक्टूबर तक अपने आप वापस आना चाहिए।",
    "audio_url": null,
    "facts": {"amount": "1,499", "amount_paise": 149900, "payee": "City Mobiles", "expected_by": "2026-10-04"}
  },
  "chips": [
    {"id": "what_if", "label": "अगर नहीं आया तो?"},
    {"id": "why", "label": "क्यों?"},
    {"id": "talk_to_human", "label": "किसी इंसान से बात करें"}
  ],
  "actions": [],
  "case": { "...": "case object, as in /v1/cases/open" },
  "messages": [
    {"id": 2, "role": "user", "kind": "reply", "text": "paise kat gaye par mila nahi", "lang": "hi",
     "ts": "2026-10-03T13:31:06+05:30", "chips": [], "actions": [], "audio_url": null},
    {"id": 3, "role": "agent", "kind": "reply", "text": "हाँ, आपके खाते से 1,499 रुपये कटे हैं, …", "lang": "hi",
     "ts": "2026-10-03T13:31:06+05:30", "chips": [ "…same as above…" ], "actions": [], "audio_url": null}
  ]
}
```

Rendering:
- Append `messages` (the user bubble, then the agent bubble).
- Play `speak.audio_url` (WAV) if it isn't `null` and the speaker isn't muted. The bubble text and the speech are always identical. The audio is generated on the first GET (about 2 s), so show the text right away and start the audio when it arrives. Stop playback when the user taps the mic (barge-in).
- Show `chips` under the newest agent bubble only.
- Re-render the case card from `case.card`.

**Chips** (`id` → what to do on tap):

| id | Action |
|---|---|
| `retry` | `POST /v1/cases/{id}/retry/confirm` (call 4) |
| `why`, `what_if`, `talk_to_human` | `POST /v1/voice/turn` with `{"case_id", "chip_id"}` |

**`end_conversation`** (boolean, on every turn response). It is `true` when the user said goodbye ("thank you", "bas", "धन्यवाद"), asked for a human, or an `OPEN_PAY_SCREEN` action was returned. A hands-free client stops listening after speaking this reply; otherwise it listens again. A goodbye turn has `intent: "goodbye"`, no chips, and changes nothing about the case.

**Off-topic questions** (coding, weather, jokes, "ignore your instructions…") come back with `intent: "off_topic"` and a reply in the user's language that points back to this payment ("Please stay relevant to this transaction. I can only help with your ₹350 payment to Sharma Medicals: …"). The case doesn't change, numbers in the question are not treated as claims, and the usual chips are returned.

**Actions**:

| type | Meaning |
|---|---|
| `OPEN_PAY_SCREEN` | Open the pay screen pre-filled with `payload` (see call 4). It only appears after the live re-check and the full retry gate pass. |

The user can also just say "yes" / "haan" / "हो" after a retry offer. The backend then runs the same confirmation as call 4 and returns `OPEN_PAY_SCREEN` in `actions`.

---

### 4. `POST /v1/cases/{id}/retry/confirm`: user tapped "Pay ₹X again"

No body is needed. The backend re-checks NPCI, the ledger and the merchant live, runs every safe-retry gate condition, then returns the pay-screen payload. Payee and amount come **only** from Paytm's own record.

```http
POST /v1/cases/c_3e989745/retry/confirm
Idempotency-Key: 0b7e…
```
```json
{
  "ok": true,
  "pay_screen": {
    "case_id": "c_3e989745",
    "retry_of_txn_id": "txn_s1_sharma",
    "payee_vpa": "sharmamedicals@paytm",
    "payee_name": "Sharma Medicals",
    "amount_paise": 35000,
    "note": "Retry of failed payment",
    "payee_source": "PAYTM_RECORD",
    "retry_id": 1
  },
  "case_id": "c_3e989745",
  "intent": "confirm_retry",
  "lang": "en",
  "user_text": "Pay ₹350 again",
  "speak": {"lang": "en", "audio_url": null,
            "text": "Paying ₹350 to Sharma Medicals. Opening the payment screen. Check the details, then enter your PIN.",
            "facts": {"amount": "350", "amount_paise": 35000, "payee": "Sharma Medicals"}},
  "chips": [],
  "actions": [{"type": "OPEN_PAY_SCREEN", "payload": { "...": "same as pay_screen" }}],
  "case": { "...": "state RETRY_CONFIRMED" },
  "messages": [ "...user bubble 'Pay ₹350 again' + agent read-back..." ]
}
```

If the world changed (for example a late debit landed), you get `"ok": false` and `"pay_screen": null`, and `speak.text` explains why ("Wait: the bank's status for this payment has just changed…"). Don't open the pay screen.

Then, on the pay screen, after the user enters a PIN (mock):

```http
POST /v1/payments
Idempotency-Key: 9a2d…
{"payee_vpa": "sharmamedicals@paytm", "payee_name": "Sharma Medicals", "amount_paise": 35000,
 "pin": "1234", "retry_of_case_id": "c_3e989745"}
```

This returns `201 {"transaction": {...status "SUCCESS"...}, "case": {... "state": "RESOLVED" ...}}`. If the payee or amount don't match the confirmed retry, it returns `409`. The PIN is any 4–6 digits and is never stored. A new agent message ("Your new payment of ₹350 to Sharma Medicals went through…") is added to the case's chat.

---

### 5. `GET /v1/cases/{id}/messages`: chat history

```json
{
  "case_id": "c_7ce63426",
  "messages": [
    {"id": 2, "role": "user", "kind": "reply", "text": "paise kat gaye par mila nahi", "lang": "hi", "ts": "…",
     "chips": [], "actions": [], "audio_url": null},
    {"id": 3, "role": "agent", "kind": "reply", "text": "हाँ, आपके खाते से 1,499 रुपये कटे हैं, …", "lang": "hi", "ts": "…",
     "chips": [{"id": "what_if", "label": "अगर नहीं आया तो?"}, "…"], "actions": [], "audio_url": null},
    {"id": 8, "role": "agent", "kind": "update",
     "text": "आपके 1,499 रुपये समय पर वापस नहीं आए, इसलिए मैंने शिकायत दर्ज कर दी है (रेफरेंस UDIR25CA9750)। बैंक को देरी के लिए 100 रुपये हर्जाना भी देना होगा।",
     "lang": "hi", "ts": "2026-10-05T13:31:06+05:30",
     "chips": [{"id": "why", "label": "क्यों?"}, {"id": "talk_to_human", "label": "किसी इंसान से बात करें"}],
     "actions": [], "audio_url": null}
  ]
}
```

### Reply audio: `GET /v1/audio/{id}`

`audio_url` is an absolute URL built from `PUBLIC_BASE_URL` (set it to the address the phone reaches, for example an HTTPS tunnel). It returns `audio/wav`. It needs no bearer header, because an `<audio>` element can't send one: the 128-bit id in the URL is the access token. `404` means unknown; `503 tts_disabled` and `502 tts_failed` mean show text only.

`kind: "update"` marks a message the agent added in the background (a dispute raised, a refund landed, a retry succeeded). This is NOTIFY (spec 6.10). Show it as the newest agent bubble. It is never spoken unprompted.

---

## Other endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/cases/{id}` | Case object + `transaction` + `timeline` (`[{ts, event}]`) |
| GET | `/v1/cases/{id}/activity` | Full audit events `[{id, ts, actor, event, payload}]` for the agent activity panel |
| GET | `/v1/briefing?exclude_case_id=&lang=` | `{"items": [{case_id, txn_id, situation, text, lang}]}` |
| POST | `/v1/cases/{id}/dispute` | Manual trigger. `200 {"raised": true, case}` only if the rules call for a dispute, otherwise `409 {"detail", "decision", "rule"}` |
| POST | `/v1/events/transactions` | Ingest a mock Paytm transaction: `{payee_vpa, payee_name, amount_paise, status, debited?, failure_code?, failure_reason?, note?, category?, mock_evidence?: {npci?, ledger?, merchant?}}` → `201 {transaction, case}`. Failed or pending payments get a case prepared immediately. |
| GET | `/v1/review/queue` | Escalated cases, each with `case_file` (summary, evidence per source, conflicts, rule trace, recommended actions, timeline) |
| POST | `/v1/review/{case_id}/decision` | `{"decision": "APPROVE"\|"REJECT"\|"REQUEST_INFO", "reviewer", "notes"}` |
| DELETE | `/v1/me/data` | Deletes the user's chat transcripts and claims |

## Mock world (`/mock/*`, demo only, no auth)

| Method | Path | Notes |
|---|---|---|
| GET | `/mock/paytm/transactions?user_id=u_demo` | Paytm records |
| GET | `/mock/npci/status?upi_ref=` | `{status: SUCCESS\|FAILED\|PENDING\|DEEMED, final, reason_code, reason, available}` |
| GET | `/mock/bank/ledger?upi_ref=` | `{state: NO_DEBIT\|DEBITED\|REVERSED, debit_count, amount_paise, debited_at, reversed_at}` |
| GET | `/mock/merchant/credit?upi_ref=` | `{credited, credit_count, credited_at}` |
| POST | `/mock/npci/udir/dispute` | `{upi_ref, kind, amount_paise}` → `{ref}` |
| GET | `/mock/npci/udir/disputes` | Raised complaints |
| GET / POST | `/mock/clock` | POST `{"advance_minutes"\|"advance_hours"\|"advance_days": n}` or `{"reset": true}`. Jobs that become due run right away (same code as the background worker): `jobs_run: [{job_id, kind, case_id, txn_id, from, to, decision, rule, status}]` |
| GET | `/mock/jobs?status=QUEUED` | The scheduler's `jobs` table: `RECHECK_CASE`, `SLA_DEADLINE`, `DISPUTE_FOLLOWUP` |
| POST | `/mock/inject` | `{"txn_id": "…", "npci"?: {status, final, reason_code}, "ledger"?: {state, debit_count}, "merchant"?: {credited}}` changes the outside world. The next action's live re-check catches it. |

## Seeded demo data (`backend/scripts/reset_db.py`)

| txn id | Payment | Prepared decision |
|---|---|---|
| `txn_s1_sharma` | ₹350 Sharma Medicals, FAILED, not debited (40 min ago) | S1: F1 → OFFER_RETRY |
| `txn_s2_citymobiles` | ₹1,499 City Mobiles, FAILED, debited (2 h ago) | S2: F4 → WAIT until T+1 end of day, then dispute + compensation |
| `txn_f3_gupta` | ₹220 Gupta Stores, PENDING (yesterday) | F3 → WAIT |
| `txn_s3_patel` | ₹2,000 Patel Electronics, FAILED; NPCI SUCCESS, no debit, merchant credited | S3: F9 → ESCALATE with case file |
| `txn_10_ramesh` | ₹10 Ramesh Tea Stall at 10:37, debited then reversed | F8 → CLOSE (update message + badge) |
| `txn_1ok_anil`, `txn_1fail_anil` | ₹1 Anil Kumar at 11:18 (success) and 11:19 ("Bad Network") | F2 → OFFER_RETRY, in its own session |
