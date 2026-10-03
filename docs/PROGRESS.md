# Progress

## Done
- **Step 1: skeleton.** `backend/` FastAPI app; pydantic-settings config (`backend/.env`, `.env.example`); SQLite with WAL + busy timeout on every connection; all spec §7 tables + `jobs`, `messages`, `idempotency_keys`, mock-world tables; append-only `case_events` (DB triggers); simulated clock; demo seed (relative dates) and `scripts/reset_db.py`; FastAPI serves `web/` at `/`.

- **Step 2: mock world.** `PaymentSource` / `EvidenceSource` / `DisputeChannel` interfaces (`app/mock/sources.py`) with DB-backed mocks; `/mock/paytm/transactions`, `/mock/npci/status`, `/mock/bank/ledger`, `/mock/merchant/credit`, `/mock/npci/udir/dispute`, `/mock/clock` (time-skip), `/mock/inject`.

- **Step 3: engine.** `app/engine/`: evidence assembler with conflict / suspicious / settling detection; rules diagnosis F1-F10 (+AMBIGUOUS); decision rules 0-8 + 7b (`decision.py`, pure); safe-retry gate with 10 named checks (`retry_gate.py`); live re-check before OFFER_RETRY / RAISE_DISPUTE / CLOSE and before returning the pay-screen payload; actions (disputes via mock UDIR, compensation, escalation case file, jobs rows, NOTIFY messages); audit events for every step. Reply templates en/hi/mr + number-check (`app/conversation/templates.py`). Seeded cases are prepared at seed time. `/mock/clock` re-decides open cases (stand-in for the step-6 scheduler). Tests: every rule, every gate condition, every class, pipeline scenarios.

- **Step 4: /v1 API.** Session tokens (HMAC, demo login), `Idempotency-Key` on mutating calls, all spec §9 routes plus `GET /v1/transactions/{id}` and `POST /v1/payments` (mock PIN pay; a retry must match the confirmed payload). Text turns via keyword intents + language detection (en/hi/mr incl. romanized), template replies with number-check, chips, `OPEN_PAY_SCREEN` action; first reply briefs disputes on other cases. Audio turns return `422 stt_disabled` until step 7. `docs/API_CONTRACT.md` written from real responses.

- **Step 5: web UI.** New phone-width app at `web/` root (`index.html`, `styles.css`, `data.js`, `app.js`, `README.md`) using the colours of `Paytm-Clone-main/` (left untouched). `TransactionRepository` / `AgentRepository` call `/v1` (async). Screens: home, history (badges), transaction details with floating AI mic, AI Resolve chat (text mode: case card, bubbles, chips, update messages), pay + mock PIN for safe retry. Checked in Chrome: S2 (City Mobiles, "paise kat gaye par mila nahi") and the full S1 retry flow.

- **Step 6: scheduler.** `app/scheduler.py`: one in-process worker thread (started with the app, `SCHEDULER_ENABLED`) polls the `jobs` table every `SCHEDULER_POLL_SECONDS`. Jobs: `RECHECK_CASE` (pending / bank-down / 7b), `SLA_DEADLINE` (F4: dispute + compensation via mock UDIR, after a live re-check), `DISPUTE_FOLLOWUP` (daily: catch late reversal and close, or grow compensation by days late). Exclusive claim via conditional UPDATE, retries with backoff, `FAILED` after `JOB_MAX_ATTEMPTS`, stale `RUNNING` jobs re-queued at startup. `/mock/clock` now runs due jobs through the same path (`jobs_run` in the response); `/mock/jobs` lists the queue. Verified on the live server with concurrent API traffic: no SQLite lock errors.
- **Step 7: voice + LLM.** Probed live first (2026-10-03):
  - **Sarvam STT:** accepts browser webm/opus only as the bare `audio/webm` type, so the adapter strips `;codecs=…`. `language_code=unknown` auto-detects. About 0.5–0.9 s.
  - **Sarvam TTS:** returns base64 WAV.
  - **`deepseek-flash`:** a reasoning model. Hidden reasoning counts toward `max_tokens`, so small budgets return empty content; `LLM_MAX_TOKENS=2000`. JSON mode works but was slower, so `LLM_JSON_MODE=false`, and the output is Pydantic-validated either way.
  - **Built:** `app/providers/` (LLM and Sarvam adapters, switchable by config) and `app/conversation/llm_tasks.py`, the only four LLM jobs:
    1. Intent, asked only when the keyword rules miss (~1 s); low confidence falls back to the status answer.
    2. Rephrase, number-checked; off by default (+2 s per reply).
    3. AMBIGUOUS classification from structured evidence only; low confidence escalates.
    4. Escalation case-file summary as a background `CASE_SUMMARY` job; numbers must appear in the case file.
  - **Voice turns:** multipart audio → STT → the same turn handler. Reply audio is generated lazily at `GET /v1/audio/{id}` and cached under `backend/media/`.
  - **Web:** `web/voice.js` listening sheet (orb, silence detection, live preview), handoff to the chat, spoken replies, barge-in, mute.
  - **Rule fix found while testing:** rule 7b no longer waits forever when NPCI evidence is *missing*; it escalates.
  - **Checked live:** a Hindi voice turn in 0.9 s; the browser flow sheet → STT → S2 answer; all four LLM jobs. Audible playback can't be confirmed in the automated browser (hidden tab); check it by hand.
- **Hands-free voice conversation (owner request, 2026-10-03).** One tap starts a Siri-style loop (listen → spoken reply → listen) instead of spec 4.2 step 6's tap per turn.
  - **It ends on:** 7 s of silence, a goodbye ("thank you / bas / धन्यवाद", new intent `goodbye`), asking for a human, the pay screen, ✕, or leaving the chat. The backend sends `end_conversation`.
  - **Safety:** the mic is still on only while a listening indicator shows. Goodbye is detected before yes/no, so "ok thanks" can never confirm a retry; "no thanks" still declines.
  - **Fix:** the voice level is measured on the audio thread (AudioWorklet), because frame-based sampling missed the follow-up turn.
  - **Checked in Chrome:** two-turn hands-free run (question → answer → auto-listen → "ठीक है, धन्यवाद" → goodbye → mic released).
  - **Follow-up (owner feedback):**
    - The wait is longer: 20 s to start talking, 2 s pauses allowed mid-sentence, 30 s per turn.
    - A no-speech clip keeps the loop listening (up to 3 misses).
    - Room noise is measured before speech counts.
    - Sarvam's 400 for empty clips now means `no_speech`, not an outage.
    - Reply text is revealed in step with the voice, with chips after it finishes.
    - The user's live words show in the chat while they speak.
    - Checked in Chrome: noise → keeps listening → question → word-by-word reply → chips → auto-listen → goodbye.

## Next
- Step 8: simulator + B0/B1/B2 evaluation (B2 = with the LLM classifier).
- Before demo: native-speaker review of Hindi/Marathi templates; verify RBI TAT/compensation values.

## Notes / decisions
- Times are naive UTC in the DB; IST (+05:30) for display and SLA end-of-day.
- SLA deadline = end of day IST, T+n after the debit date (n from config).
- Spec 4.2 step 6 (tap the mic for every turn) is replaced by hands-free conversation; see above. Consider recording this in CLAUDE.md's team decisions.
- A user's "money was debited" statement is not treated as suspicious on its own (honest confusion is common); amount/payee mismatches and repeat claims are.
- Hindi/Marathi templates need a native speaker's review.
