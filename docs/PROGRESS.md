# Progress

## Done
- **Step 1: skeleton.** `backend/` FastAPI app; pydantic-settings config (`backend/.env`, `.env.example`); SQLite with WAL + busy timeout on every connection; all spec §7 tables + `jobs`, `messages`, `idempotency_keys`, mock-world tables; append-only `case_events` (DB triggers); simulated clock; demo seed (relative dates) and `scripts/reset_db.py`; FastAPI serves `web/` at `/`.

- **Step 2: mock world.** `PaymentSource` / `EvidenceSource` / `DisputeChannel` interfaces (`app/mock/sources.py`) with DB-backed mocks; `/mock/paytm/transactions`, `/mock/npci/status`, `/mock/bank/ledger`, `/mock/merchant/credit`, `/mock/npci/udir/dispute`, `/mock/clock` (time-skip), `/mock/inject`.

- **Step 3: engine.** `app/engine/`: evidence assembler with conflict / suspicious / settling detection; rules diagnosis F1-F10 (+AMBIGUOUS); decision rules 0-8 + 7b (`decision.py`, pure); safe-retry gate with 10 named checks (`retry_gate.py`); live re-check before OFFER_RETRY / RAISE_DISPUTE / CLOSE and before returning the pay-screen payload; actions (disputes via mock UDIR, compensation, escalation case file, jobs rows, NOTIFY messages); audit events for every step. Reply templates en/hi/mr + number-check (`app/conversation/templates.py`). Seeded cases are prepared at seed time. `/mock/clock` re-decides open cases (stand-in for the step-6 scheduler). Tests: every rule, every gate condition, every class, pipeline scenarios.

- **Step 4: /v1 API.** Session tokens (HMAC, demo login), `Idempotency-Key` on mutating calls, all spec §9 routes plus `GET /v1/transactions/{id}` and `POST /v1/payments` (mock PIN pay; a retry must match the confirmed payload). Text turns via keyword intents + language detection (en/hi/mr incl. romanized), template replies with number-check, chips, `OPEN_PAY_SCREEN` action; first reply briefs disputes on other cases. Audio turns return `422 stt_disabled` until step 7. `docs/API_CONTRACT.md` written from real responses.

- **Step 5: web UI.** New phone-width app at `web/` root (`index.html`, `styles.css`, `data.js`, `app.js`, `README.md`) using the colours of `Paytm-Clone-main/` (left untouched). `TransactionRepository` / `AgentRepository` call `/v1` (async). Screens: home, history (badges), transaction details with floating AI mic, AI Resolve chat (text mode: case card, bubbles, chips, update messages), pay + mock PIN for safe retry. Checked in Chrome: S2 (City Mobiles, "paise kat gaye par mila nahi") and the full S1 retry flow.

## Next
- Step 6: SLA/dispute scheduler: one in-process worker polling the `jobs` table (rows are already written for WAIT decisions); move the time-skip re-decide into it.
- Step 7: LLM adapter (intent/rephrase with number-check), Sarvam STT/TTS, listening sheet with live transcript.
- Step 8: simulator + B0/B1/B2 evaluation.
- Before demo: native-speaker review of Hindi/Marathi templates; verify RBI TAT/compensation values.

## Notes / decisions
- Times are naive UTC in the DB; IST (+05:30) for display and SLA end-of-day.
- SLA deadline = end of day IST, T+n after the debit date (n from config).
- A user's "money was debited" statement is not treated as suspicious on its own (honest confusion is common); amount/payee mismatches and repeat claims are.
- Hindi/Marathi templates need a native speaker's review.
