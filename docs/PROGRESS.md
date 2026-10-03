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
  - **It ends on:** silence (now 20 s, see the follow-up below), a goodbye ("thank you / bas / धन्यवाद", new intent `goodbye`), asking for a human, the pay screen, ✕, or leaving the chat. The backend sends `end_conversation`.
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

- **Step 8: simulator + evaluation.** `app/sim/`, run with `scripts/run_sim.py`; results in `docs/EVALUATION.md` and `docs/evaluation.json`, and the run is recorded in `sim_runs` / `sim_cases`.
  - **Generator:** labelled cases for F1–F10 with noise:
    - stale Paytm records;
    - a source outage;
    - disagreements still inside the allowed lag;
    - the world changing between the decision and the action (late debit, reversal landing);
    - adversarial claims and repeat claimants.
  - **Answer key:** each case's acceptable actions come from the scenario, not from the engine.
  - **Baselines:** B0 (record only), B1 (+ all evidence + live re-check) and B2 (+ LLM classifier, live `deepseek-flash`, cached per distinct evidence pattern).
  - **Results (3000 cases, seed 7):**
    - B0: false-retry rate 27.8%.
    - B1 and B2: false retries 0 and false actions 0.
    - The re-check cancelled 95 actions, all of which would have been wrong.
    - B2 lifts diagnosis accuracy from 93.1% to 96.5%.
  - **Cross-check:** 500 cases also ran through the real `process_transaction` on a throwaway DB (with the world switching before the re-check). They agree 100% with the simulator loop.
  - **Right payment:** the spec 1.0 sequence over HTTP attaches the right payment 50/50.
  - **Safety bug found by B2, fixed:** with a source down, an LLM class (F7, F8, F4 past deadline) went through rules 2/3/5/6 and raised disputes or closed cases, against spec 8.3. Now an LLM-sourced diagnosis can only lead to WAIT or ESCALATE (`decision.py`, `LLM_ALLOWED_ACTIONS`), and a test runs B2 with a reckless fake LLM.
  - **Known failure, reported and left for the team:** a payment that really succeeded, but whose Paytm record still says FAILED, is escalated as a record-vs-NPCI conflict (53 needless escalations).

- **Review console.** `web/console.html` + `console.js`, served at `/console.html`.
  - **Live:** the app in a phone frame next to the agent activity panel. The panel follows the most recently active case and shows readable audit steps, each tagged with the agent's job (spec 6.9).
  - **Review queue:** the full case file, and Approve / Reject / Request info.
  - **Numbers:** the evaluation.
  - **Backend:** `GET /v1/review/cases`, `GET /v1/review/cases/{id}` and `GET /v1/review/evaluation`.
  - **Reviewer decisions now reach the user:**
    - a fixed `update` message in their language (en/hi/mr, `templates.REVIEW`), plus the history badge;
    - the new `REVIEWED` situation, with status line "Reviewed by a specialist";
    - the notes stay internal.
  - Checked with headless-Chrome screenshots of all three tabs.
- **Step 9: demo polish.**
  - `docs/DEMO.md` maps every spec §17 beat (hook, S1, S2, S3, numbers, close, optional outage and late debit) to exact clicks and words, plus the test that covers it.
  - `POST /mock/scenario`:
    - `bank_outage` fails a new payment with the bank down, prepared as F6 → WAIT with no human;
    - `late_debit` makes the S1 "yes" hit the live re-check.
  - Both have API tests and console buttons.

- **"Talk to a human" rings the support line** (owner request, 2026-10-03).
  - **Setting:** `HUMAN_SUPPORT_PHONE` (in `backend/.env` only; validated as +country digits).
  - **Backend:** a `talk_to_human` turn escalates as before, replies "connecting you to a support specialist" (`templates.CALLING`, en/hi/mr, no digits spoken), and returns a `CALL_HUMAN` action.
  - **Web:** a call card, and `tel:` is opened after the reply is spoken. The Expo shell hands `tel:` to Android's dialer.
  - **Limit:** Expo Go can only open the dialer (one tap to call). A no-tap call needs `CALL_PHONE` in a standalone APK.
  - **Checked in Chrome:** reply → card with +91 number → `tel:` navigation. Tests: 230 pass.
- **Three agents instead of six, and payee names in the UI language** (owner request, 2026-10-03).
  - **Agents:** Bank (NPCI + ledger + merchant), Rules (diagnosis, rule, retry safety, deadline, live re-check) and Follow-up. The removed agents' content is folded in, not dropped.
  - **Payee names:** in Devanagari for hi / mr via a reviewed word dictionary (`app/conversation/names.py`, not the LLM). An unknown word keeps the original name. This applies to lists, the case card, replies, agents, the scan screen and the retry pay screen (`payee_display`). Payments keep `payee_name`.
  - **Checked in Chrome with the Marathi UI.** Tests: 227 pass.
- **Spoken language wins over the UI language for voice replies** (owner choice, 2026-10-03, after Marathi mid-chat got an English answer on the phone).
  - What happened: Sarvam had identified `mr-IN` with probability 1.0, but the EN toggle won.
  - Now a voice turn with language-ID probability ≥ `SPOKEN_LANG_MIN_PROBABILITY` (0.8) is answered in the spoken language; otherwise the UI language applies.
  - Tests for both cases.
- **Phone app (Expo SDK 57, Android): `mobile/`** (owner request, 2026-10-03). A WebView shell around `web/`, so the phone shows exactly the same app.
  - **Native side:**
    - a server-address screen, remembered in AsyncStorage;
    - the mic permission is requested up front (`expo-audio`), and the page's `getUserMedia` is granted;
    - replies play automatically (`mediaPlaybackRequiresUserAction=false`);
    - the Android back button works.
  - **Tunnel:** the phone reaches the laptop through a cloudflared HTTPS tunnel (`mobile/tunnel.ps1`), because the mic needs HTTPS.
  - **Backend:** `PUBLIC_BASE_URL` now defaults to empty, so audio links are relative and work through any tunnel.
  - **Checks:**
    - `expo-doctor` 21/21; the Android bundle exports.
    - The full flow was run through a real quick tunnel over HTTPS (scan → failed → six agents → spoken conclusion → listening); both reply audios were served.
    - Not yet run on a physical phone.
- **Investigation by six agents + UI language toggle** (owner request, 2026-10-03; CLAUDE.md decisions 3 and 4). This replaces the "Would you like me to check?" offer below.
  - **Investigation:**
    - After a Scan & Pay failure, `/v1/cases/open {"investigate": true}` returns an intro, six agents (Network, Bank, Diagnosis, Rules, Safety, Follow-up) and a conclusion.
    - Every line is a template filled from real records (`app/conversation/investigation.py`).
    - The Safety agent reports the live re-fetch made while opening. Its silent trigger `USER_INVESTIGATE` avoids a duplicate update message.
  - **Web:** a Grok-style `InvestigationPanel`. Agents appear one by one with "thinking" dots, then their lines and a verdict badge; the spoken conclusion follows, then hands-free listening.
  - **Language:**
    - EN/हिं/मरा toggle in every header; all UI text is in `I18N` (`data.js`).
    - `X-UI-Lang` makes replies, status lines, next actions and failure reasons follow the UI language (`app/i18n.py`, a request contextvar).
  - **Checked in headless Chrome (Hindi UI):** scan → pay → failed → investigation, 2/6 mid-way then 6/6 → Hindi conclusion and chips → listening.
  - **Tests:** 223 pass.
- **The agent speaks first after a failure in front of the user** (mentor feedback, 2026-10-03; CLAUDE.md team decision 3). The offer step was replaced by the investigation above.
  - **Flow:** Home → Scan & Pay (mock viewfinder, `POST /v1/scan`) → amount → PIN → the payment fails on purpose (`DEMO_SCAN_PAY_FAILURE`, default `debited` → F4) → failure screen about 2 s → the chat opens.
  - **The offer:** `/v1/cases/open` with `offer_help` adds one message, in the user's language (`templates.OFFER`, en/hi/mr), with chips "Yes, please help" / "No, thanks" and TTS. The app speaks it, then starts the hands-free loop.
  - **Answers:** only an explicit short "no" ends the conversation; anything else, "yes" included, gets the status answer. A "yes" to the offer can never confirm a retry; this is tested on a RETRY_OFFERED case.
  - **Checked in headless Chrome over CDP:** home → scan → amount → PIN → failed → chat with the spoken offer (Sarvam audio served) → Listening….
  - **Tests:** 223 pass.

## Next
- Rehearse `docs/DEMO.md` with real voice; record the fallback clip.
- Decide whether "record FAILED, but NPCI SUCCESS + debited + credited" should CLOSE instead of escalating (see EVALUATION.md).
- Before demo: native-speaker review of Hindi/Marathi templates; verify RBI TAT/compensation values.

## Notes / decisions
- Times are naive UTC in the DB; IST (+05:30) for display and SLA end-of-day.
- SLA deadline = end of day IST, T+n after the debit date (n from config).
- Spec 4.2 step 6 (tap the mic for every turn) is replaced by hands-free conversation; see above. Consider recording this in CLAUDE.md's team decisions.
- A user's "money was debited" statement is not treated as suspicious on its own (honest confusion is common); amount/payee mismatches and repeat claims are.
- Hindi/Marathi templates need a native speaker's review.
