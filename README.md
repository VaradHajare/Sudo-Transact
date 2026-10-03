# Sudo Transact

**A voice-first AI support teammate inside Paytm that resolves failed and pending UPI payments end to end, in Hindi, Marathi and English.**

Paytm Hackathon · Track 3: Autonomous AI Teammates. Prototype: every payment system is mocked and no real money moves.

> UPI Help needs you to describe the problem. Our agent lives inside Paytm, already knows what happened when you open it, tells you in your own language, retries safely when it's safe, and chases the bank in the background when it isn't.

## What it does

A floating AI mic button appears on a failed or pending payment. You tap it once and talk, Siri-style. The agent already knows **which** payment you mean, answers out loud, and keeps the conversation going.

| Scenario | What happens |
|---|---|
| **S1: failed before debit** | "No money was taken. Pay again?" → read-back → live re-check → pre-filled pay screen → you enter your PIN |
| **S2: debited, not credited** | "₹1,499 was debited but didn't reach City Mobiles. Don't pay again; it should come back by 4 October." If the bank misses the deadline, the agent raises a dispute and flags compensation in the background, and you see it in that payment's chat. |
| **S3: sources disagree** | The agent refuses to act and escalates to a human with a full case file. |

**Core principle: rules decide; the LLM never moves money.** The case taxonomy (F1–F10), decision rules 0–8 (+7b), the safe-retry gate, the live re-check before every action, the SLA/dispute tracker and the audit log are all deterministic code. The LLM does only four things:
1. understands vague questions;
2. optionally rephrases replies, with every number checked against the facts;
3. classifies cases the rules can't place, where low confidence escalates;
4. writes the reviewer's case summary.

It also fixes a bug we saw in Paytm's current support chat: **one session per payment**, bound to the payment on screen, so a new failure never lands in an old conversation.

## Run it

Needs Python 3.12+ (developed on 3.14). Chrome is recommended for the mic.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env            # then add your keys (see "Configuration")
.venv\Scripts\python scripts\reset_db.py
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**. Tap **Scan & Pay**, enter an amount and any PIN. The payment fails on purpose (demo), and the AI agent opens and asks if you need help. Or tap **City Mobiles ₹1,499 → mic**, and say or type `paise kat gaye par mila nahi`. On Home, **Skip time +1 day** (twice) moves the mock clock past the deadline to show the automatic dispute.

For the pitch, open **http://localhost:8000/console.html**. It shows the app in a phone frame next to the live agent activity panel, plus the review queue and the evaluation numbers. The full demo script, click by click, is in [`docs/DEMO.md`](docs/DEMO.md).

To re-run the evaluation: `.venv\Scripts\python scripts\run_sim.py` (3,000 cases; add `--no-llm` to skip B2). Results go to [`docs/EVALUATION.md`](docs/EVALUATION.md).

To run the tests: `cd backend && .venv\Scripts\python -m pytest`, which runs 223 tests and makes no network calls.

### Configuration (`backend/.env`, never committed)

| Group | Variables |
|---|---|
| LLM (OpenAI-compatible; DeepSeek by default) | `LLM_ENABLED`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_MAX_TOKENS`, `LLM_MIN_CONFIDENCE`, per-job switches |
| Sarvam voice | `SARVAM_API_KEY`, `STT_ENABLED`, `TTS_ENABLED`, `SARVAM_TTS_SPEAKER` |
| Decision rules | `COMPENSATION_PER_DAY`, `SLA_*_DAYS`, `PENDING_WINDOW_MINUTES`, `RETRY_COOLDOWN_SECONDS`, … |
| App | `DATABASE_URL` (SQLite only), `PUBLIC_BASE_URL`, `DEMO_MODE`, `SCHEDULER_ENABLED` |

With LLM / STT / TTS switched off, everything still works on templates and text. See `backend/.env.example` for the full list.

## Repository layout

```
backend/            FastAPI app (Python), SQLite, tests
  app/engine/       evidence, diagnosis F1–F10, decision rules, retry gate, re-check, actions, audit
  app/conversation/ intents, en/hi/mr templates + number-check, LLM jobs, turn handler
  app/providers/    Sarvam STT/TTS and LLM adapters (switchable by config)
  app/mock/         mock Paytm / NPCI / bank / merchant / UDIR + clock time-skip
  app/api/v1/       REST API for the app
  app/scheduler.py  background SLA / dispute worker (jobs table)
web/                demo app (plain HTML/CSS/JS, served by FastAPI at /)
docs/SPEC.md        product spec (v2.4)
docs/API_CONTRACT.md request/response examples for every endpoint
docs/PROGRESS.md    detailed build log and decisions
```

Stack: FastAPI + Pydantic, SQLAlchemy on SQLite (WAL), an in-process job worker instead of Redis, Sarvam (`saaras:v4` STT, `bulbul:v3` TTS) and DeepSeek `deepseek-flash`. LangGraph wrapping of the agent loop isn't done yet.

## Progress

| Step | Status | What it covers |
|---|---|---|
| 1. Skeleton | ✅ Done | Config, SQLite models, append-only audit log, simulated clock, demo seed + reset script |
| 2. Mock payment world | ✅ Done | Paytm records, NPCI, bank ledger, merchant credit, UDIR disputes, clock time-skip, state injection |
| 3. Decision engine | ✅ Done | Evidence + conflict detection, F1–F10 diagnosis, rules 0–8 / 7b, 10-condition safe-retry gate, live re-check, escalation case file. Every rule and gate condition is tested. |
| 4. API | ✅ Done | `/v1` (spec §9) + session tokens + idempotency keys; `docs/API_CONTRACT.md` |
| 5. Web app | ✅ Done | Home, history (badges), transaction details with the floating mic, AI chat, pay + mock PIN |
| 6. Background scheduler | ✅ Done | Deadline disputes, compensation that grows per late day, closing on a late refund, without the user |
| 7. Voice + LLM | ✅ Done | Sarvam STT/TTS with auto language, hands-free Siri-style conversation, reply text following the voice, the 4 LLM jobs |
| Extras | ✅ Done | Off-topic questions redirected in the user's language; "thank you / धन्यवाद" ends the conversation; noise-robust listening |
| 8. Simulator + evaluation | ✅ Done | 3,000 generated cases. False retries: B0 (record only) 670, B1/B2 **0**. Wrong closes/disputes: 0. The re-check cancelled 95 wrong actions. Right payment attached: 100%. See `docs/EVALUATION.md`. |
| Review console | ✅ Done | `/console.html`: phone + live agent activity panel, review queue (decisions reach the user's chat), numbers |
| 9. Demo polish | ✅ Done | `docs/DEMO.md` maps every spec §17 beat to clicks and a test; bank-outage and late-debit demo buttons (`/mock/scenario`) |

### Still remaining
- **A rule decision for the team:** should a payment that really succeeded, but whose Paytm record still says FAILED, be closed instead of escalated? (53 needless escalations in the evaluation.)
- **Rehearse `docs/DEMO.md`** with real voice in the room, and record the fallback clip.
- **Content checks before the demo:** native-speaker review of the Hindi and Marathi templates; verify RBI turnaround and compensation values (T+1, ₹100/day in config) against the current circular; check UPI Help's current status for the comparison slide.
- **Phone demo:** an HTTPS tunnel (for example cloudflared) for mic access on a phone, with `PUBLIC_BASE_URL` set to it.
- **Optional:**
  - wrap the pipeline in LangGraph;
  - streaming STT for a server-side live transcript (the browser preview is used today);
  - the Kotlin app port, against the same API;
  - SMS evidence (spec §15, stretch).

## Notes
- **Prototype only.** All payment systems are mocked, it is labelled "Prototype · mock data, no real money", and the mock PIN is never stored.
- **Privacy:** no user audio is stored. Transcripts are redacted of long digit sequences, the audit log keeps intents and timings but not text, and `DELETE /v1/me/data` removes chat transcripts and reply audio. The live words preview in the listening sheet uses the browser's speech recognizer (Google in Chrome); only Sarvam's transcript is used. It can be turned off in `web/data.js`.
- `web/Paytm-Clone-main/` is the team's original Paytm-style site, kept as is; the app reuses its colours.
