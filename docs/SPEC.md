# Voice-First Failed UPI Payment Resolution Agent (built into Paytm) — Technical Spec

**Team:** Sudo Transact (Sahil Singh, Varad Hajare)
**Track:** Autonomous AI Teammates (customer-service workflow, end to end)
**Form factor:** an AI feature inside Paytm, opened from a floating AI mic button that appears at the bottom of the screen when a payment fails or is pending
**Data approach:** all external systems mocked (Paytm records, NPCI status, bank ledger, merchant credit); own simulator for evaluation
**Status:** Draft v2.4 (SMS reading moved to stretch scope)

> **Changes in v2.4:** test sequence in 1.0 corrected to what actually happened: the chat was still tied to the earlier ₹10 conversation, and Support gave no way to start a new chat for the new failure. Gap rows in 1.0, 4.0, 1.1 and the demo hook (17) reworded to match.

> **Changes in v2.3:** problem statement rewritten from what we saw testing Paytm's current support (1.0); positioning now compares against Paytm's own Customer Care chat (1.1); design principles that answer each gap (4.0); bank-outage load handled through F6 answers rather than incident grouping; demo hook uses a before/after with the real flow (17).

> **Changes in v2.2:** new entry and interface: a floating AI mic button (Siri-style) appears at the bottom when a payment fails or is pending; tapping it shows a live transcript of what the user says, then expands into a full chat screen where the conversation continues by voice, with every turn shown as chat bubbles (4.1, 4.3, 10.1). The first agent reply answers the user's question and includes the briefing.

> **Changes in v2.1 (small fixes on the agreed v2):**
> - Rule gap fixed: an F1/F2 case that fails the retry gate only because status isn't final now **waits** instead of escalating (8.2, rule 7b).
> - Live re-check before every action added (8.5, rule 0).
> - On-demand case assembly when the user opens a payment that hasn't been prepared yet (6.3).
> - "What the AI teammate does" made explicit for the track pitch (6.9). No change to what rules decide.
> - Agent activity panel added to the console for the demo (6.8).
> - `NOTIFY` defined (6.10). Assumption: no push notifications; open question for the team.
> - Merchant marked as stretch; "mock refunds/advances" removed (not in the action list); S2 dialogue made briefing-first; Sarvam named as a voice candidate.

---

## 1. Summary

### 1.0 The problem we observed

When a UPI payment goes wrong, the user can't tell whether to wait, retry or complain. Most cases are technical and resolve under RBI turnaround timelines, but the status is opaque, deadlines are not tracked per user, and support treats clear glitches and suspicious cases alike.

We tested Paytm's current flow ourselves (3 Oct 2026):

1. Opened Customer Care about the ₹10 payment made at 10:37 AM and chatted until about 11:16 AM, partly in Marathi; the bot replied in Marathi.
2. Made a ₹1 payment (11:18 AM), which succeeded.
3. Made another ₹1 payment (11:19 AM), which failed with "Bad Network".
4. Tapped Support. There was no option to start a new chat, so we were back in the same thread and asked about our "last payment".

| What happened | Why it's a problem |
|---|---|
| Support offered **no way to start a new chat**; it reopened the old thread about the ₹10 payment | One session for everything: a new problem lands inside an old conversation |
| We wrote "issue regarding last payment". The bot kept talking about the **₹10 payment from 10:37 AM**, not the **₹1 payment that failed at 11:19 AM** | The session stays tied to whichever payment opened it and never notices that a newer payment just failed |
| The bot asked us to **describe the problem again**, even though the app already has the failed payment's details | The user does the work the app should do |
| Help is a **typed chat**, reached from a menu; the mic only dictates text and replies are text | Hard for elderly or less tech-comfortable users, who need to speak and listen, not type and read |
| No way to reach a person by phone from the chat | During a **bank outage**, thousands of users hit the same few channels; human queues can't absorb it |

**So the problem is:** a user whose payment just failed has no simple, spoken, native-language way to ask "what happened to my money?" and get an answer about *that* payment. And when a bank is down, human support is swamped by the same question from thousands of people.

**What we change:**
- **Right payment, automatically:** the mic button appears on the failed payment itself, so the agent already knows which payment the user means.
- **One session per payment:** each failed payment gets its own conversation, kept separate from older issues.
- **Speak and listen:** one tap, talk in Hindi, Marathi or English, and hear the answer. Text is shown too, but typing is never needed.
- **Absorbs outage spikes:** the agent answers every affected user at once with the same correct answer ("your bank is having trouble, your money is safe, don't retry"), so humans only handle real edge cases.

We build an AI teammate **inside Paytm** that:

1. **Prepares every failed or pending case in the background** from Paytm's own transaction record plus NPCI and bank status, so the case is ready before the user asks.
2. **Decides** wait / retry / expect reversal / dispute / escalate. Rules decide. The LLM handles only ambiguity, conversation and explanations. **The LLM never moves money.**
3. **Talks to the user by voice** in Hindi, Marathi and English, through a Siri-style mic button that opens into a chat screen. It **speaks only after the user taps the button**; it already knows the case, so its first reply answers the user's question and briefs them.
4. **Enforces deadlines in the background:** raises a dispute and flags compensation when a bank misses its timeline, without the user doing anything.
5. **Offers a safe retry:** when the evidence confirms no debit happened, it opens a pre-filled payment inside Paytm. The user enters their own PIN.
6. **Escalates** unclear or suspicious cases to a human with a complete case file.

### 1.1 Positioning against what already exists

**Paytm's own Customer Care chat** (the baseline we tested in 1.0) already has an AI chatbot with mic dictation. It works as one ongoing typed thread with no way to start a new chat, stays tied to the payment it was opened for, and asks the user to describe the issue. Ours starts from the failed payment, keeps one session per payment, and talks back by voice.

NPCI's **UPI Help** (AI assistant for status checks and UDIR complaints, chat/voice, English first) and **Hello! UPI** (voice-enabled payments) also exist. Ours differs because it is **native to the payment app**:

- It reads Paytm's **own transaction records** and NPCI/bank status, so the user doesn't have to describe, look up or enter anything.
- It is **already briefed when opened** and enforces **deadlines in the background**.
- It makes the **wait / retry / dispute** decision, not just a status report.
- It **triages for humans** with a full case file, and offers a **safe in-app retry**.

> Verify before submission: UPI Help's current rollout and language status, so the comparison is accurate.

### 1.2 One-line pitch

> UPI Help needs you to describe the problem. Our agent lives inside Paytm, already knows what happened when you open it, tells you in your own language, retries safely when it's safe, and chases the bank in the background when it isn't.

---

## 2. Goals and non-goals

### Goals
- End-to-end pipeline on mock data: detect → assemble evidence → diagnose → decide → re-check → act → notify → escalate.
- A Paytm-style host app with a floating AI mic button on failed/pending payments, a live-transcript listening sheet and a voice-first chat screen (text fallback).
- Safe-retry gate with an in-app pre-filled pay screen.
- Deadline tracking and automatic disputes with a demo time-skip control.
- Reviewer console showing escalated cases with evidence, plus a live agent activity panel.
- Our own measured evaluation on a few thousand simulated cases.

### Non-goals
- Real NPCI, bank, Paytm or gateway integrations (all mocked and labelled as mocked).
- Moving real money. Disputes go to mock endpoints only.
- Reproducing the real Paytm app. We build only the screens this feature touches.
- **SMS reading** is **not part of the core scope** (see section 15: future scope / if time permits).
- Merchant-facing features (stretch only).
- iOS support, Play Store distribution.
- Claiming real-world accuracy or real failure distributions. Our numbers are simulator numbers.

---

## 3. Users and scenarios

| User | Need | Example |
|---|---|---|
| **Payer** | Know what happened and what to do | Opens a failed ₹350 payment: "Did it go through?" |
| **Human reviewer** (Paytm ops) | Handle only genuine edge cases, evidence ready | Reviews an escalated conflict case |
| *Merchant (stretch)* | *Know whether a customer's payment is coming* | *"Did the ₹350 from the last customer arrive?"* |

### Demo scenarios
- **S1 Safe retry:** payment failed before debit → agent offers retry → pre-filled pay screen.
- **S2 Debited, not credited:** agent says wait and gives a date → deadline passes (time-skip) → dispute raised, compensation flagged → user sees it in the case's chat when they reopen it.
- **S3 Suspicious / conflict:** sources disagree or the claim looks abusive → agent refuses to act → escalated with case file.

---

## 4. Product behaviour

### 4.0 Design principles (each answers a gap in 1.0)

| Gap we saw | Principle |
|---|---|
| Bot stayed on the old ₹10 case and didn't notice the new ₹1 failure | **Bound to the payment on screen.** The session opens with that transaction already loaded; the user never has to say which one |
| No option to start a new chat; old and new issues share one thread | **One session per payment.** Each failed or pending payment has its own conversation and history; a new failure starts a new session |
| User asked to describe the problem | **The app speaks first with facts.** The first reply already knows status, amount, payee and what to do |
| Typed chat is hard for elderly users | **Voice-first, one tap.** Big mic button, spoken replies, simple words, text shown alongside; typing optional |
| Replies switch language | **Reply in the user's language.** Detected from what they say; stays consistent until they switch |
| Outage floods human support | **AI answers everyone instantly; humans get only the edge cases**, each with a case file |

### 4.1 Entry: the floating AI mic button
- **Where it appears:** a round, softly pulsing mic button docked at the bottom centre of the screen, with a one-line hint above it ("Payment failed? Ask me"), on:
  - the **payment failed / pending result screen**, right after the payment,
  - the **Transaction details** screen of any failed or pending payment,
  - **Payment history**, when the user has an open case (button opens the most urgent one).
- **What it knows:** the button is bound to the transaction on screen, so the agent already has that case loaded before the user speaks. The user never has to say which payment.
- **Secondary entry (optional):** a Help entry that opens the chat with a list of the user's open cases.
- The agent is **silent until the user taps the button**. No outbound calls, voice notes or audio push.

### 4.2 Interaction flow

```
 [Payment failed screen]
          │  tap mic button
          ▼
 ① LISTENING (bottom sheet)     orb animates with voice level; live transcript appears word by word
          │  user stops talking (silence ~1.5 s) or taps the orb
          ▼
 ② EXPAND to full-screen chat   user's transcribed words become the first chat bubble
          │
          ▼
 ③ AGENT REPLIES                "thinking" dots → reply bubble streams in + is spoken aloud
          │                     action chips under the reply (e.g. "Pay ₹350 again", "Talk to a human")
          ▼
 ④ CONTINUE                     tap mic to speak again (or type); tap a chip; or close
```

**Details**
1. **Tap → listen immediately.** No greeting first: the user is already asking something. A bottom sheet rises with the animated orb and the live transcript.
2. **End of speech.** Detected by about 1.5 s of silence, or the user taps the orb. A "cancel" swipe-down discards it.
3. **Expand.** The sheet grows into the full chat screen. The transcript becomes the user's first message bubble; the user can tap it to correct the text before it's sent (optional, P2).
4. **First reply = answer + briefing.** The case is already prepared, so the first reply answers the question directly and adds anything urgent on other open cases (e.g. "Also, I raised a dispute for your ₹120 payment yesterday"). If the case isn't prepared yet, it's assembled on demand (6.3) while the "thinking" dots show.
5. **Speak and show.** Every agent reply appears as a bubble **and** is spoken. The bubble's text is the same text as the speech, so nothing is lost if the sound is off.
6. **Continue.** After the agent finishes speaking, the mic button at the bottom of the chat is ready; the user taps to talk again. A keyboard icon switches to typing. Tapping the mic while the agent is speaking stops the speech (barge-in).
7. **Actions as chips.** When the decision engine allows an action, it appears as a chip under the reply ("Pay ₹350 again", "Talk to a human"). The user can tap the chip or say "yes". Money-related chips always come after a spoken read-back (8.4).
8. **Close and resume.** Closing returns to the previous screen. The conversation is saved per case; reopening shows the history, with any new update (e.g. dispute raised) as the newest agent message at the bottom.

### 4.3 Host app screens (Paytm-style prototype)

| Screen | Contents |
|---|---|
| Home | Static tiles, Help entry |
| Pay screen | Payee, amount, mock PIN step; used for normal payments and pre-filled retries |
| **Payment result** | Success / failed / pending state; **floating AI mic button** on failed or pending |
| Payment history | List from the mock backend, including failed and pending items; a badge on items with case updates; mic button when a case is open |
| Transaction details | Status, amount, payee, case status line, **floating AI mic button** |
| **Listening sheet** | Animated orb, live transcript, cancel |
| **Agent chat screen** | Pinned case card at the top (payee, amount, status, next action, expected-by date); chat bubbles; "thinking" indicator; action chips; mic button + keyboard toggle at the bottom; speaker mute; "talk to a human" in the menu |

Everything else (recharge, wallet, scan and pay) is a stub or omitted. Visual fidelity is secondary: the right structure and colours are enough.

### 4.4 Branding
> Branding: a Paytm-style look is probably expected since the problem statement is Paytm's, but check the hackathon's asset rules and label the build a prototype.

---

## 5. System architecture

```
 ┌───────────────────────────┐
 │ Paytm-style host app      │   Failed payment → floating AI mic → listening sheet → chat screen
 │ (Android, Kotlin/Compose) │──────────────┐
 └───────────────────────────┘              ▼
                                     ┌──────────────┐        ┌──────────────────────┐
 Mock Paytm event feed ────────────▶ │  FastAPI     │◀──────▶│ PostgreSQL           │
 (simulator)                         │  gateway     │        │ (cases, evidence,    │
                                     └──────┬───────┘        │  immutable audit)    │
                                            │ Redis streams  └──────────────────────┘
                                            ▼
                         ┌─────────────────────────────────────┐
                         │ Orchestrator (LangGraph)            │
                         │ Detection → Evidence assembler →    │
                         │ Diagnosis (rules + LLM) →           │
                         │ Decision engine (rules) →           │
                         │ Live re-check                       │
                         └──────┬───────────┬──────────┬───────┘
                                │           │          │
                       ┌────────▼───┐ ┌─────▼─────┐ ┌──▼────────────┐
                       │ Voice /    │ │ Dispute + │ │ Escalation +  │
                       │ briefing + │ │ SLA       │ │ case file     │
                       │ retry      │ │ tracker   │ │               │
                       └────────────┘ └─────┬─────┘ └──┬────────────┘
                                            ▼          ▼
                          Mock NPCI / bank / merchant   Console (Next.js):
                          (status, ledger, UDIR)        review queue + activity panel
```

**Pre-computation:** the Detection step runs on the incoming (mock) event stream, so cases are assembled and decided in the background. Opening the app reads prepared state, which is why the agent can brief the user without being asked.

---

## 6. Components

### 6.1 Paytm-style host app (Android)
- Single Kotlin/Jetpack Compose app: a thin shell plus the **agent module**.
- Talks only to our FastAPI backend. No API keys in the app; the backend issues a short-lived session token.
- Voice: microphone capture with **live transcription** (see 10.2), TTS playback with barge-in, and a **text-input fallback** for every flow.
- Agent UI module: floating mic button component, listening sheet, chat screen (bubbles, streaming reply text, action chips, pinned case card). Built once and reused on every screen that shows the button.
- Retry: navigates to the in-app pre-filled pay screen (see 8.4). A real UPI deep link is available behind a flag as an optional proof.

### 6.2 Backend gateway (FastAPI)
- Validates payloads (Pydantic), authenticates sessions, applies idempotency keys.
- Writes events to Postgres, pushes work items onto Redis streams.

### 6.3 Evidence assembler
Builds the `evidence_bundle` for a transaction from these sources (all mocked behind an `EvidenceSource` interface):

| Source | Gives |
|---|---|
| Paytm transaction record | Payer, payee VPA/name, amount, status, timestamps, failure code |
| NPCI status (mock) | SUCCESS / FAILED / PENDING / DEEMED, failure reason |
| Bank ledger (mock) | Debit / credit / reversal state at the issuer |
| Merchant credit (mock) | Whether the merchant received the credit |
| *Optional later:* bank SMS | Second source from the user's phone (section 15) |

**Conflicts detected:** record vs NPCI vs ledger vs merchant disagree beyond an allowed lag; amount mismatch; payee mismatch between the user's claim and the record; repeat-claim pattern.

**On-demand assembly:** if the user opens a payment whose case isn't prepared yet (e.g. it failed seconds ago), `/v1/cases/open` assembles and decides it synchronously while the chat shows the "thinking" indicator.

### 6.4 Diagnosis (rules + LLM)
Classifies the case into the taxonomy (8.1). Rules handle known patterns. The LLM is invoked only when rules return `AMBIGUOUS`; its output is constrained to a JSON schema (class, confidence, reasons[]). Low confidence → escalate.

### 6.5 Decision engine (deterministic)
Maps class + evidence + clock to an action (8.2). **No LLM in this step.**

### 6.6 Voice and briefing layer
See section 10.

### 6.7 Dispute and SLA tracker
- Per case: `debit_time`, `deadline_ts` (from the rules config), `state`.
- A backend scheduler runs whether or not the app is open. On a missed deadline it runs the live re-check (8.5), then creates a dispute through the mock UDIR endpoint and a compensation record.
- Compensation = configured per-day amount × days beyond the deadline (default ₹100/day per the RBI table in our deck; verify the current circular).
- The user learns about it from the new agent message in that case's chat, the case status line and the history badge (6.10).
- A **time-skip control** lets the demo show a deadline breach live.

### 6.8 Escalation, review console and activity panel
- Escalation builds a **case file**: timeline, evidence from each source, conflicts, rule trace, LLM reasoning (if used), recommended action.
- Console (Next.js): queue, case detail, approve / reject / request-info, outcome logged. Reviewer decisions are stored as labels (feedback loop, P2).
- **Agent activity panel (for the demo):** a live view of the current case next to the phone: evidence fetched from each source, conflicts, the rule that fired, the re-check result, the action taken, the briefing text. It reads from `case_events`, so it is cheap to build and makes the agent's work visible to judges.

### 6.9 What the AI teammate does (for the track pitch)
Rules decide what is allowed; the agent does the work around them:

| Job | What the agent does |
|---|---|
| Prepare | Detects failed/pending payments and assembles evidence before the user asks |
| Brief | Answers the user's first question from the prepared case and adds urgent items from other cases |
| Converse | Handles follow-ups ("why?", "what if it doesn't come back?"), language switching, "talk to a human" |
| Resolve ambiguity | Classifies cases the rules can't (schema-constrained) and escalates when unsure |
| Follow through | Watches deadlines, raises disputes, flags compensation, reports back on next open |
| Hand off | Writes the case file summary for the human reviewer |

Pitch line: **"The AI does the work; rules decide what it's allowed to do."**

### 6.10 What `NOTIFY` means
The agent never speaks unprompted, so `NOTIFY` updates what the user sees next time they look:
- the case card and the case status line on the Transaction details screen,
- a badge on the item in Payment history (and the mic button shown there),
- a new agent message at the bottom of that case's chat, which is also the first thing mentioned in the next reply.

> Open question: whether to also send a **text-only** push notification (e.g. "Dispute raised for your ₹350 payment"). Current assumption: no push.

---

## 7. Data model (PostgreSQL)

```
users(id, language_pref, created_at)
transactions(id, upi_ref, payer_user_id, payee_vpa, payee_name,
             amount_paise, status, failure_code, initiated_at, updated_at)
evidence_items(id, txn_id, source,            -- PAYTM_RECORD|NPCI|BANK_LEDGER|MERCHANT|SMS(optional)
               status, detail_json, observed_at)
cases(id, txn_id, user_id, class, state, decision, deadline_ts,
      confidence, has_unseen_update bool, created_at, closed_at)
case_events(id, case_id, ts, actor, event_type, payload_json)   -- APPEND-ONLY audit log
retries(id, case_id, offered_at, accepted bool, payload_json)
disputes(id, case_id, mock_udir_ref, raised_at, status)
compensation_claims(id, case_id, days_late, amount_paise, status)
reviews(id, case_id, reviewer, decision, notes, decided_at)
sim_runs(id, config_json, started_at)
sim_cases(id, run_id, ground_truth_class, txn_id, expected_action)
```

**Rules**
- Money in **paise** (integers). Never floats.
- `case_events` is append-only (DB permissions/trigger). Every rule firing, LLM call, re-check, voice turn and action is an event.
- Audio is not stored by default; transcripts are redacted of long digit sequences.

---

## 8. Decision logic

### 8.1 Case taxonomy

| Class | Meaning | Typical signals (record / NPCI / ledger / merchant) | Default action |
|---|---|---|---|
| `F1_DECLINED_PRE_DEBIT` | Failed before debit (balance, limit, wrong PIN) | FAILED / FAILED / no debit / no credit | Explain; offer safe retry |
| `F2_TIMEOUT_PRE_DEBIT` | Timed out, never debited | TIMEOUT / FAILED or no final / no debit after window | Safe retry if gate passes; otherwise wait |
| `F3_PENDING` | Outcome unknown | PENDING / PENDING / – | Wait, recheck on schedule |
| `F4_DEBIT_NO_CREDIT` | Debited, merchant not credited | any / FAILED or PENDING / DEBITED / no credit | Wait for auto-reversal; dispute at deadline |
| `F5_DEEMED_SUCCESS` | Pending that later succeeds | PENDING → SUCCESS / DEEMED / DEBITED / credited | Close; **no retry, no dispute** |
| `F6_BANK_DOWNTIME` | Issuer/beneficiary bank unavailable | FAILED / bank-unavailable code / – | Wait / retry later |
| `F7_DUPLICATE_DEBIT` | Same intent debited twice | – / – / two debits / one credit | Dispute the duplicate |
| `F8_ALREADY_REVERSED` | Money already back | – / – / REVERSED | Close; inform user |
| `F9_CONFLICT` | Sources contradict (e.g. NPCI SUCCESS but ledger shows no debit) | inconsistent | Escalate |
| `F10_SUSPICIOUS` | Abuse or fraud-like (claim contradicts ledger, repeat claims, payee mismatch) | claim vs evidence mismatch | Escalate; no automated action |

### 8.2 Decision rules (ordered, first match wins)

```
0.  live re-check (8.5) found a changed state             → RE-ASSEMBLE + RE-DIAGNOSE
1.  conflicts non-empty OR class in {F9, F10}             → ESCALATE
2.  class == F8 (reversal confirmed)                      → CLOSE + NOTIFY
3.  class == F5 (deemed success)                          → CLOSE + NOTIFY
4.  class in {F3, F6}                                     → WAIT (schedule recheck)
5.  class == F4:
      now < deadline_ts                                   → WAIT + NOTIFY expected-by date
      now >= deadline_ts                                  → RAISE_DISPUTE + COMPENSATION_CLAIM + NOTIFY
6.  class == F7                                           → RAISE_DISPUTE (duplicate) + NOTIFY
7.  class in {F1, F2} AND retry_gate_passes               → OFFER_RETRY
7b. class in {F1, F2} AND gate fails only on status finality,
      pending window, or cooldown                         → WAIT (schedule recheck)
8.  otherwise                                             → ESCALATE (unknown)
```

Deadlines and windows live in a **rules config**, not in code:
```yaml
sla:
  beneficiary_credit_failure:    { auto_reversal_by_days: 1, compensation_per_day: 100 }
  merchant_confirmation_missing: { auto_reversal_by_days: 5, compensation_per_day: 100 }
pending_window_minutes: 30     # assumption, tune in the simulator
retry_cooldown_minutes: 10
max_retries_per_txn: 1
```
> Verify the SLA values against the current RBI circular before citing them.

### 8.3 What the LLM may and may not do

| Allowed | Not allowed |
|---|---|
| Classify when rules return AMBIGUOUS (schema-constrained) | Trigger disputes or retries |
| Compose the briefing and rephrase explanations in the user's language | Generate amounts, dates or deadlines (these come from templates) |
| Hold a multi-turn conversation | Override the decision engine |
| Draft the escalation summary | Receive untrusted free text as instructions |
| Parse intent/entities from voice transcripts | |

### 8.4 Safe-retry gate

**All** must be true to offer a retry:
1. Class is `F1` or `F2` (failed before debit).
2. NPCI status is a **final FAILED** and the bank ledger confirms **no debit**; the pending window has elapsed.
3. No conflicts in the evidence bundle.
4. Payee VPA and name come from the **Paytm transaction record** (or a QR the user scanned).
5. Cooldown passed and `max_retries_per_txn` not exceeded.
6. **Live re-check passes** (8.5) right before the offer is spoken and again before the pay-screen payload is returned.
7. The user confirms by voice or tap after the agent reads back payee and amount.

If any condition fails: no retry. If state is pending or unclear: say "wait" (rule 7b).

**In-app retry:** the app opens the Pay screen pre-filled with payee and amount. The user checks the details and enters their PIN (mock in the prototype).

**Optional proof (flag):** a real UPI deep link, tested on a phone, can open a real UPI app pre-filled:
```
upi://pay?pa=<payee_vpa>&pn=<url-encoded name>&am=350.00&cu=INR&tn=Retry%20of%20failed%20payment
```
App behaviour differs (risk warnings, editable amount), so test each app and keep the in-app screen as the primary path.

### 8.5 Live re-check before every action

A case can be decided in the background minutes or hours before the user acts on it, and the world may have changed (a reversal landed, a pending payment succeeded). Immediately before any action, the system re-fetches NPCI status, bank ledger and merchant credit:

- **When:** before speaking a retry offer, before returning the pay-screen payload, before raising a dispute or compensation claim, and before closing a case.
- **If anything changed** from the evidence the decision used: cancel the action, log `RECHECK_CHANGED`, re-assemble and re-diagnose (rule 0).
- **Otherwise:** log `RECHECK_PASSED` and proceed.

---

## 9. API surface

Versioned under `/v1`. JSON. Session-token auth. `Idempotency-Key` header on mutating calls.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/transactions` | Payment history for the host app (with case badges) |
| POST | `/v1/events/transactions` | Ingest a (mock) Paytm transaction event |
| POST | `/v1/cases/open` | User tapped the mic button → returns prepared case (assembles on demand if needed) |
| GET | `/v1/briefing` | Urgent items across the user's open cases, folded into the first reply |
| POST | `/v1/voice/turn` | One turn (audio or text) → agent reply (text, audio, action chips) |
| GET | `/v1/cases/{id}/messages` | Saved chat history for the case |
| GET | `/v1/cases/{id}` | Case state, timeline, next action |
| GET | `/v1/cases/{id}/activity` | Live agent activity for the console panel |
| POST | `/v1/cases/{id}/retry/confirm` | User confirmed retry → re-check → pay-screen payload |
| POST | `/v1/cases/{id}/dispute` | Manual trigger (normally scheduler-driven) |
| GET | `/v1/review/queue` | Escalated cases |
| POST | `/v1/review/{id}/decision` | Reviewer decision |
| DELETE | `/v1/me/data` | Delete the user's stored transcripts and case data |

**Voice turn response**
```json
{ "case_id": "c_123", "decision": "WAIT",
  "user_text": "मेरा पेमेंट फेल हो गया, पैसे कटे क्या?",
  "speak": { "lang": "hi", "text": "...", "audio_url": "/v1/audio/a_456",
             "facts": {"amount": "350", "expected_by": "2026-10-06"} },
  "chips": [ { "id": "talk_to_human", "label": "Talk to a human" } ],
  "actions": [] }
```

### Mock layer endpoints (internal, `/mock/*`)
| Path | Simulates |
|---|---|
| `/mock/paytm/transactions` | Paytm's own transaction records and event feed |
| `/mock/npci/status?upi_ref=` | SUCCESS / FAILED / PENDING / DEEMED, with failure reason |
| `/mock/bank/ledger?upi_ref=` | Debit / credit / reversal state at the issuer |
| `/mock/merchant/credit?upi_ref=` | Whether the merchant was credited |
| `/mock/npci/udir/dispute` | Accepts a dispute, returns a reference |
| `/mock/clock` | Time-skip control for the demo |
| `/mock/inject` | Change a payment's state on demand (to demo the re-check) |

All sit behind `EvidenceSource` / `PaymentSource` interfaces so real or sandbox adapters could replace them later without changing agent code.

---

## 10. Voice layer

### 10.1 Session start
The agent is silent until the user taps the floating mic button (4.1). It starts **listening immediately**, with no greeting, because the user is already asking something. The case for the payment on screen is loaded in the background, so the first reply answers the question and adds any urgent items from other open cases (4.2).

### 10.2 Pipeline
```
tap mic → audio stream → live transcript on screen (partial results)
        → end of speech (silence ~1.5 s or tap) → final transcript → user bubble
        → intent/entity extraction (LLM, JSON schema) → case lookup → decision engine (facts)
        → response template per language (facts inserted) → optional LLM rephrase
        → reply bubble (text) + TTS (audio) + action chips
```
- **Live transcript:** needs speech-to-text that returns partial results while the user talks. Use the chosen provider's streaming mode if it has one; otherwise use Android's on-device speech recognizer for the live text and send the final text to the backend. Check that Hindi and Marathi are supported in whichever path you pick.
- **Reply latency:** show the reply text as soon as it's ready and start audio right after; show "thinking" dots in between. Target: reply text within about 2 s of the user stopping.
- **Barge-in:** tapping the mic while the agent is speaking stops the audio and starts listening.
- **Facts (amounts, dates, actions) always come from templates filled by the decision engine.** The LLM may only rephrase tone, then a check confirms the numbers in the output match the facts. The spoken text and the bubble text are identical.
- Text-mode fallback for every flow: the keyboard icon in the chat, and the whole flow works with the speaker muted.

### 10.3 Languages
English, Hindi, Marathi. The agent replies in the language the user spoke; the user can switch mid-conversation. Choose STT/TTS providers by testing at least two options (Sarvam, a hackathon sponsor built for Indian languages, as one of them) on recordings of your own demo speakers, and record word-level accuracy before committing.

### 10.4 Intents
`status_check`, `what_should_i_do`, `why`, `confirm_retry`, `decline_retry`, `raise_dispute`, `repeat`, `talk_to_human`. (`merchant_check` only if the merchant stretch is built.)

### 10.5 Example conversations

**S1 Safe retry** — user taps the mic on the failed ₹350 payment to Sharma Medicals
> User (spoken, transcribed live): "Did my money get cut?"
> Agent (bubble + voice): "No. Your ₹350 payment to Sharma Medicals didn't go through, and no money was taken from your account. Would you like to pay again?" *[chip: Pay ₹350 again]*
> User: "Yes."
> Agent: "Paying ₹350 to Sharma Medicals. Opening the payment screen. Check the details, then enter your PIN."

**S2 Debited, not credited (Hindi)**
> User: "मेरा पेमेंट फेल हो गया, पैसे कटे क्या?"
> Agent: "हाँ, आपके खाते से 350 रुपये कटे हैं, लेकिन शर्मा मेडिकल्स को नहीं पहुंचे। दोबारा पेमेंट मत कीजिए। यह पैसा 6 अक्टूबर तक अपने आप वापस आना चाहिए।"
> User: "अगर नहीं आया तो?"
> Agent: "तो मैं अपने आप शिकायत दर्ज कर दूँगा, और यहीं आपको बता दूँगा।"

**S2, reopening after the deadline** — the chat history shows the earlier conversation, and the newest agent message is:
> Agent: "आपके 350 रुपये समय पर वापस नहीं आए, इसलिए मैंने शिकायत दर्ज कर दी है। बैंक को देरी के लिए हर्जाना भी देना होगा।"

(Have a native speaker review Hindi and write Marathi templates before the demo.)

### 10.6 Voice safety
- Read back payee and amount before any retry; require an explicit yes (spoken or chip tap).
- "Talk to a human" is always available (menu and chip).
- The agent never speaks unprompted. Audio starts only after the user taps the mic.
- The microphone is on only while the listening indicator is visible.
- No audio stored by default.

---

## 11. Safety, privacy, abuse

| Area | Control |
|---|---|
| Money movement | None real. Caps and human-approval thresholds enforced in the decision engine |
| Retry safety | Gate in 8.4; payee from the Paytm record; live re-check; read-back; user enters the PIN |
| Stale decisions | Live re-check before every action (8.5) |
| Idempotency | Keys on disputes, retries, notifications; no double actions |
| Abuse | Claim vs ledger mismatch, repeat-claim detection, payee mismatch → escalate |
| Prompt injection | Untrusted text (voice transcripts, any future SMS) is never given to tools as instructions; LLM output is schema-validated; actions come only from the decision engine |
| Privacy | Mock data only in the prototype; no audio stored; transcripts redacted; delete-my-data endpoint |
| Audit | Append-only `case_events`; LangSmith traces for LLM calls |
| Disputes | Raised through the (mock) bank/NPCI channel. We don't claim to refund money directly |

---

## 12. Mock layer and simulator

### 12.1 Purpose
Generate labelled cases to (a) drive the demo and (b) produce our own evaluation numbers. The simulator emits **ground truth** per case, so accuracy is measurable.

### 12.2 Generator
Inputs: `n_cases`, class mix, seed.

Per case it creates:
- a Paytm transaction record (payer, payee VPA/name from a fake directory, amount, timestamps),
- consistent mock NPCI status, bank ledger and merchant-credit responses for the class,
- timing: reversals that arrive on time, late, or never; pending states that resolve to success or failure,
- state changes between decision and action, to test the live re-check,
- noise: delayed or briefly inconsistent statuses (within an allowed lag),
- adversarial cases: claims that contradict the ledger, repeat claimants, payee mismatches, impossible status combinations.

### 12.3 Class mix
Configurable. The default mix is an **assumption for testing**, not a real-world statistic; say so in the pitch. Keep rare classes (F7, F10) common enough to measure.

### 12.4 Time control
`/mock/clock` advances simulated time so reversals arrive (or don't) and deadlines pass during the demo.

---

## 13. Evaluation plan

### 13.1 Baselines
1. **B0:** rules on the Paytm transaction record only.
2. **B1:** B0 + NPCI status + bank ledger + merchant credit.
3. **B2:** B1 + LLM for ambiguous cases (full system).

B0 → B1 → B2 shows what the extra evidence and the LLM each add.

### 13.2 Metrics
| Metric | Why |
|---|---|
| Diagnosis accuracy per class + confusion matrix | Core correctness |
| **False-retry rate** (retry offered on a debited/pending payment) | Safety-critical; target **0** |
| **False-action rate** (wrong dispute/close) | Safety-critical |
| Actions cancelled by the live re-check | Value of re-checking |
| Escalation rate and escalation precision | Human workload and appropriateness |
| SLA breaches caught / compensation flagged | Enforcement value |
| Time to a prepared answer when the user opens the app | Responsiveness |
| Right payment attached to the session (should be 100%, since it's bound to the screen) | The core gap we saw in Paytm's current chat |
| Turns until the user has a clear answer (target: 1) | Effort for the user, especially elderly users |
| Share of outage-time cases answered without a human | Load taken off human support |
| Voice: intent accuracy, word error rate on our sample set | Voice quality |

### 13.3 Reporting rules
- Report simulator numbers as simulator numbers.
- Report failures too (which classes confuse).
- Treat `false_retry_rate > 0` as a bug to fix, not a number to explain.

---

## 14. Tech stack

| Layer | Choice | Purpose |
|---|---|---|
| Agent engine | LangGraph | Stateful workflow, tool calls, human-in-the-loop interrupts |
| Backend | FastAPI + Pydantic | Ingestion, strict validation |
| Queue | Redis streams | Decouple ingestion from processing |
| DB | PostgreSQL | ACID storage, append-only audit |
| Observability | LangSmith | Trace reasoning and tool calls |
| Host app | Kotlin + Jetpack Compose | Paytm-style shell, floating mic button, listening sheet, chat screen |
| Console | Next.js | Reviewer UI + activity panel |
| Voice | STT/TTS: Sarvam + one alternative, chosen by testing on real recordings | Multilingual voice |
| Deploy | Docker Compose | One-command stack |

> If time gets tight: a `jobs` table polled by a scheduler can replace Redis streams, and SQLite can replace PostgreSQL, without changing the rest of the design.

---

## 15. Stretch scope: bank SMS as a second evidence source (future scope / if time permits)

**Not part of the core build.** Do this only after P0–P2 are stable.

### 15.1 What it adds
A second, independent source of truth from the user's phone: the bank's debit alert, reversal alert, or silence. It would let the agent cross-check Paytm's record against what the bank told the user (e.g. a reversal SMS means "don't dispute").

### 15.2 How it plugs in
It is just another `EvidenceSource` (`source = SMS`). No change to the taxonomy or decision engine beyond using the extra evidence. It adds an optional table and endpoint:
```
sms_evidence(id, user_id, idem_key, bank_code, kind, amount_paise, upi_ref,
             payee_vpa, event_time, received_at, parse_confidence)
POST /v1/sms   -- extracted fields only
```

### 15.3 Design (if built)
- Android: `RECEIVE_SMS` / `READ_SMS`, a `BroadcastReceiver` for live capture, and an inbox backfill **on every app open** (the reliable path, since some phones kill background receivers).
- Filter on-device: bank/UPI sender allowlist (configurable, include a test sender for the demo); **drop OTP-like messages before logging, storing or parsing**.
- Parse on the phone with regex for 3–4 bank formats taken from **real alerts on your own phones**. Send only extracted fields (amount, ref, kind, time, bank), never raw text.
- Consent screen, off switch, delete-my-data (DPDP-aligned).

### 15.4 Trust rules
- SMS is **untrusted evidence**: never executes instructions in text, and never triggers an action alone.
- **Absence of an SMS proves nothing**: bank alerts can arrive late.
- A payee VPA parsed from SMS is **never** used to build a retry (8.4 stays: record or QR only).
- Unknown sender, malformed fields, or SMS with no matching transaction → conflict → escalate.

### 15.5 Caveats
- Sideload only: Play Store restricts SMS permissions. On newer Android, a sideloaded app may need "Allow restricted settings" in App info, or install via `adb`.
- Android only; iOS apps can't read SMS.
- RCS chats aren't readable; bank alerts are normally plain SMS, but check real messages on your phones.
- In a real Paytm deployment, SMS access would be Paytm's decision under platform policy. Don't claim it as a given.

### 15.6 Phase-0 check (15 minutes)
A minimal app that logs only sender IDs from the last few hours of the inbox. If the bank's sender shows up, the approach works.

### 15.7 Extra metrics if built
False-dispute rate with vs without SMS; SMS parse accuracy per bank format.

---

## 16. Build plan (two people)

Suggested split (adjust to strengths): **A = backend, agents, simulator, evaluation. B = host app, voice, console.**

| Tier | Items |
|---|---|
| **P0: must work for any demo** | Simulator + mock layer; ingestion + detection; taxonomy + decision engine; live re-check; cases + audit log; dispute/SLA tracker with time-skip; escalation case file; minimal console |
| **P1: the differentiators** | Host app shell (pay, result, history, details); floating mic button + listening sheet with live transcript + chat screen (bubbles, chips, case card); chat in text mode first; safe-retry gate + in-app pay screen; activity panel; evaluation run (B0/B1/B2) |
| **P2: polish** | Real STT/TTS with live partial transcript; barge-in; second language; edit-transcript-before-send; reviewer-feedback loop; optional real deep-link proof |
| **P3: stretch / pitch only** | **SMS evidence (section 15)**; QR scan for payee capture; merchant-side view; per-bank reliability dashboard; WhatsApp notifications; production Paytm integration |

### Order of work
1. **Day-0 checks:** deep link test with a ₹1 payment between teammates (optional proof); STT test on your own voices in Hindi/Marathi (Sarvam + one alternative).
2. Simulator + mock layer + decision engine + live re-check + audit log (P0).
3. Escalation, SLA tracker with time-skip, console (P0).
4. Host app shell with static then live data; chat screen working in text mode (P1).
5. Floating mic button + listening sheet, safe retry (P1).
6. Activity panel (P1; reads `case_events`).
7. Evaluation run; record results (P1).
8. Real voice, then polish (P2).
9. Section 15 only if time remains.
10. Rehearse the demo with a fallback for every live step.

Build the shell last with static data first; pixel-perfect UI is the biggest time sink.

---

## 17. Demo script

Two screens: the phone (mirrored) on one side, the agent activity panel on the other.

1. **Hook (30 s), before / after:** show our real test: a payment fails, Support reopens the old chat about an earlier ₹10 payment with no option to start fresh, we ask about "last payment", and the bot keeps talking about the ₹10 payment and asks us to explain. Then: "Here's the same moment with our teammate." Keep the tone factual; it's the host's product.
2. **S1 Safe retry:** make a payment in the Paytm-style app → it fails → the mic button appears at the bottom → tap and ask "Did my money get cut?" (live transcript on screen) → chat opens: "No money was taken. Pay again?" → "Yes" → read-back → re-check passes → pre-filled pay screen → PIN.
3. **S2 Debited, not credited:** tap the mic on another failed payment and ask in Hindi → the agent says wait and gives the date → user asks "what if it doesn't come back?" → advance the mock clock past the deadline → re-check → dispute raised and compensation flagged → reopen the payment: the new message is in the chat and the history shows a badge.
4. **S3 Suspicious:** a claim that contradicts the ledger → the agent refuses to act → escalated case file in the console.
5. **Numbers:** B0 → B1 → B2, false-retry rate, actions cancelled by re-check, confusion matrix.
6. **Close:** the one-line pitch and "The AI does the work; rules decide what it's allowed to do." Say plainly what is mocked and what is real.

*Optional (if time), bank outage:* mark the payer bank as down in the mock layer and fail a few payments from different demo users. Each user taps the mic and immediately gets the same correct F6 answer ("your bank is having trouble, your money is safe, don't pay again"), while the console shows no human escalations. This shows the outage load being absorbed without the incident-grouping feature.

*Optional (if time):* in S1, inject a late debit just before the user confirms → the re-check catches it → the agent says "wait" instead of opening the pay screen.

**Fallbacks:** text mode if voice fails; recorded clip if the host app crashes; seeded data so each scenario is repeatable.

---

## 18. Risks and things to verify

| Risk / unknown | Mitigation |
|---|---|
| Judges see "a rules engine with voice" | Show the agent's jobs (6.9) live in the activity panel; use the pitch line |
| Overlap with UPI Help / Hello! UPI | Position as Paytm-native, already knows the case when you tap, background enforcement, safe retry, triage; name them first |
| Weaker "proactive" angle (no unprompted voice) | Pitch as "already knows the case when you tap + background deadline enforcement", not "calls you first" |
| Live transcript is slow or wrong on stage | Test partial-result STT early in Hindi/Marathi; headset mic; keyboard fallback in the chat |
| Decision goes stale between background decision and user action | Live re-check (8.5) |
| Fake-Paytm UI eats time | Build only the screens this feature touches; shell last |
| Branding / asset rules | Check hackathon rules; label as a prototype |
| STT quality in Marathi/Hindi | Test on real speakers; text fallback |
| SLA numbers out of date | Keep in config; verify against the current RBI circular |
| Simulator results look "too good" | Include noisy and adversarial cases; report failures; label as simulated |
| Scope creep for two people | Hold the P0/P1/P2 line; SMS stays in P3 |

### Verification checklist before submission
- [ ] UPI Help's current status and languages
- [ ] RBI TAT and compensation wording (cite the circular)
- [ ] One sourced volume figure (RBI Ombudsman annual report), described accurately as complaints reaching the Ombudsman, not Paytm tickets
- [ ] Hackathon rules on Paytm-style UI assets
- [ ] Hindi/Marathi templates reviewed by a native speaker
- [ ] If SMS is built: permission works on the demo phone; consent wording reviewed

---

## 19. Glossary

- **UPI Ref / RRN:** unique reference of a UPI transaction.
- **VPA:** Virtual Payment Address (UPI ID).
- **UDIR:** NPCI's UPI dispute redressal framework.
- **TAT / T+n:** turnaround time of n days after the transaction date.
- **Deemed success:** a pending transaction that later resolves as successful.
- **PSP / TPAP:** payment service provider / third-party app provider.
- **Case file:** the evidence package given to a human reviewer.
- **Live re-check:** a fresh fetch of a payment's state immediately before an action.