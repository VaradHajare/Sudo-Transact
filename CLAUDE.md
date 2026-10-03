# Sudo Transact: Paytm Hackathon (Track 3, Autonomous AI Teammates)

Voice-first AI support teammate inside Paytm. It resolves failed or pending UPI payments end to end, in Hindi, Marathi and English, and escalates to a human only when needed.

**The full spec is `docs/SPEC.md` (v2.4). Read it before building anything. If this file and the spec disagree, THIS FILE wins: it records team decisions made after the spec.**

## Team decisions that override the spec
1. **The demo app is the web prototype in `web/`** (plain HTML/CSS/JS, no framework, no build step), not Kotlin. Wherever the spec says Kotlin / Jetpack Compose, read "the web app in `web/`". A Kotlin port may come later, so keep the API clean and app-agnostic.
2. **SQLite, not Postgres. A jobs table, not Redis.** Do not set up Postgres or Redis.
3. **The agent speaks first when a payment fails in front of the user** (mentor feedback, 3 Oct 2026). This replaces "speaks only after the user taps" (spec 1.0, 6.10) for that moment only.
   - Flow: Scan & Pay fails (on purpose in the demo, `DEMO_SCAN_PAY_FAILURE`), then the chat opens: "Your payment failed. I'm running a detailed investigation."
   - Six agents then appear one at a time, each showing its thinking: Network (NPCI), Bank (ledger + merchant credit), Diagnosis (F1-F10), Rules (decision), Safety (live re-check), Follow-up (deadline / dispute).
   - Then the spoken conclusion, then the normal hands-free follow-up.
   - Every agent line comes from real records (`app/conversation/investigation.py`). Never invent agent output.
   - The mic button on failed payments stays.
4. **Reply language: what the user clearly spoke, else the UI language.**
   - The app has an EN / हिं / मरा toggle in every header. It sends `X-UI-Lang`, and screens, status lines, the investigation and replies to typed text follow it.
   - A voice turn whose spoken language Sarvam identifies with at least `SPOKEN_LANG_MIN_PROBABILITY` (0.8) is answered in that spoken language. Switching to Marathi mid-chat gets Marathi; the toggle does not change.
   - Without the header, replies follow the detected language.

## Repo layout
```
CLAUDE.md
docs/SPEC.md            the product spec
docs/PROGRESS.md        what is done and what is next (keep updated)
docs/API_CONTRACT.md    request/response examples for every endpoint
backend/                FastAPI app, tests, .env
web/                    the demo UI (index.html, app.js, data.js, styles.css, assets)
mobile/                 Expo (Android) shell that shows web/ in a WebView over an HTTPS tunnel, for the phone demo
```

## Team
- Paresh (owner): backend, agentic features, and wiring the web UI to the backend. You work for Paresh.
- Sahil: built the web UI. Read `web/README.md` before touching it.

## Core principle
**Rules decide; the LLM never moves money.** The LLM may only:
1. extract intent and entities from the user's speech,
2. converse and rephrase (numbers and dates always come from templates, followed by a number-check),
3. classify AMBIGUOUS cases as JSON (low confidence means escalate),
4. write the escalation case file.

Everything else is deterministic code: case taxonomy F1-F10, decision rules 0-8 (including 7b WAIT), the safe-retry gate, live re-check (8.5) before any action, the SLA/dispute tracker, and the audit log.

## Stack
FastAPI + Pydantic, LangGraph for the agent, SQLite via SQLAlchemy, a jobs table for background work, Docker Compose optional. The Next.js review console is lower priority (a simple page in `web/` is fine).

SQLite rules:
- Turn on WAL mode and a busy timeout (e.g. 5 s) on every connection. The SLA scheduler and the API write at the same time.
- Use only portable SQLAlchemy types: no JSONB, arrays or other Postgres-only features. Store JSON as text.
- Background jobs (SLA checks, dispute follow-ups) go in a `jobs` table polled by one in-process worker.
- Provide a reset script that deletes the DB file and re-seeds the demo data.

## Web UI rules (`web/`)
- **FastAPI serves `web/` as static files** at `/`, so the UI and API share one origin (no CORS, no `file://`). Open the app at `http://localhost:8000/`.
- Keep Sahil's conventions: no frameworks, no CDN, no build step, all design tokens in the `:root` block of `styles.css`, components as render functions with a props comment, `BRAND` is the only place the app name appears, amounts are integer paise.
- `window.TransactionRepository` in `data.js` becomes the API client. Its methods become async (return Promises), so update the screens in `app.js` that call it (show a loading state). Keep the transaction field names (camelCase: `id, payeeName, payeeVpa, amountPaise, status, debited, timestamp, note, direction, category, railLabel`) so the API response matches the existing UI shape.
- The backend is the source of truth for diagnosis. The UI must never decide "safe to retry" from its own `debited` field; it shows the backend's decision.
- Screens still to build, in the existing visual style:
  - **#/txn/:id Transaction details**: SUCCESS / FAILED / PENDING variants, plus the **floating AI mic button** on FAILED and PENDING (spec section 4).
  - **Listening sheet**: opens from the mic button, records audio, shows the live transcript.
  - **#/agent/:id AI Resolve chat**: voice-first chat (bubbles, action chips, pinned case card), one session per payment, bound to that transaction id. Text input as a fallback.
  - **#/pay/:id Pay + mock PIN**: needed for the safe-retry flow.
- Microphone: use `getUserMedia` + `MediaRecorder` and send the audio to `POST /v1/voice/turn`. Browsers only allow the mic on `localhost` or HTTPS: demo on the laptop, or use an HTTPS tunnel (e.g. cloudflared) for a phone. Always offer a text fallback.
- Play TTS audio with an `<audio>` element from the `audio_url` in the voice-turn response.

## Demo data fixes
Seed these in the backend (the backend owns the data now, and `data.js` only keeps the formatters):
- Keep all of Sahil's transactions, but move the three problem payments to recent dates so they are inside dispute timelines: Sharma Medicals (FAILED, not debited → S1/F1), City Mobiles (FAILED, debited → S2/F4), Gupta Stores (PENDING → F3) to today and yesterday.
- Add the real-world case from spec 1.0: an outgoing ₹1 payment that FAILED today at 11:19 AM, next to the earlier ₹10 payment at 10:37 AM.
- Mock evidence (NPCI status, bank ledger, merchant credit) for each problem payment must make the diagnosis come out as intended.

## Providers
- Agent LLM: DeepSeek V4.1 Flash, model `deepseek-flash`, OpenAI-compatible API. Keep it behind a switchable setting (base URL + model name + key in config) so Sarvam's LLM or Claude can replace it. JSON mode for this model is unconfirmed: test it first and validate output with Pydantic regardless.
- STT: Sarvam `POST https://api.sarvam.ai/speech-to-text`, header `api-subscription-key`, multipart `file`, model `saaras:v4`, `language_code` hi-IN / mr-IN / en-IN. Browser MediaRecorder produces webm/ogg: convert to WAV (e.g. ffmpeg) if Sarvam rejects it. A realtime WebSocket also exists for the live transcript.
- TTS: Sarvam `POST https://api.sarvam.ai/text-to-speech`, JSON `text` (max 2500 chars), `target_language_code`, `speaker` (default `shubh`), model `bulbul:v3`. Returns base64 WAV in `audios[]`: save it and serve it from `audio_url`.
- Keys go in `backend/.env`. Never commit it, and make sure it is in `.gitignore`.

## Config
All settings come from `.env` through a single settings module (pydantic-settings). Never hard-code thresholds; read them from config. Keep `.env.example` in sync, with the same variable names and no secrets. Key groups: app/session, `DATABASE_URL`, LLM (`LLM_ENABLED`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_JSON_MODE`, `LLM_TIMEOUT_SECONDS`), Sarvam (`SARVAM_*`, `STT_ENABLED`, `TTS_ENABLED`), decision rules (`COMPENSATION_PER_DAY`, `PENDING_WINDOW_MINUTES`, `RETRY_COOLDOWN_SECONDS`, `LLM_MIN_CONFIDENCE`), `PUBLIC_BASE_URL`, `DEMO_MODE`, `SEED_DEMO_DATA`. When `LLM_ENABLED`, `STT_ENABLED` or `TTS_ENABLED` is false, fall back to templates or text so the app still works.

## Build order
1. Skeleton, config, SQLite models, reset/seed script, FastAPI serving `web/`.
2. Mock payment world: `/mock/paytm/transactions`, `/mock/npci/status`, `/mock/bank/ledger`, `/mock/merchant/credit`, `/mock/clock` (time-skip), `/mock/inject`, behind `PaymentSource` / `EvidenceSource` interfaces.
3. Evidence assembler, diagnosis (F1-F10), decision engine, safe-retry gate, live re-check, audit log. Pytest for every rule and gate condition.
4. `/v1` API (spec section 9) and `docs/API_CONTRACT.md`.
5. Wire the web UI: `TransactionRepository` → API, then the transaction details screen, mic button, agent chat (text first), pay + PIN for safe retry.
6. SLA/dispute scheduler and the mock UDIR dispute endpoint.
7. Agent conversation layer (LLM adapter, template + number-check), then Sarvam STT/TTS and the listening sheet.
8. Simulator and B0/B1/B2 evaluation (target: false-retry rate 0, right-payment attachment 100%).
9. Demo polish: the S1/S2/S3 scenarios and the spec section 17 demo script run end to end.

## Hard rules
- One session per payment, bound to the payment on screen. Never attach a new failure to an old chat. This is the real Paytm bug we are fixing.
- No real money, no real bank or NPCI calls. Everything is mocked.
- Write tests for the decision rules and the retry gate before the LLM layer.
- Commit after each working step. Keep `docs/PROGRESS.md` updated.
