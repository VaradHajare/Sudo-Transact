# web/: demo UI (prototype)

A phone-width web app for the AI Resolve feature. Plain HTML, CSS and JS: no framework, no CDN, no build step. FastAPI serves this folder at `/`, so open **http://localhost:8000/** (same origin as the API, no CORS).

`Paytm-Clone-main/` is Sahil's original Paytm-style site. It stays untouched; its colours (`#00baf2`, `#002970`, `#f5f7fa`) are the design tokens here. It's still served at `/Paytm-Clone-main/`.

## Files
| File | What |
|---|---|
| `index.html` | Shell: `#app` root, hidden `<audio id="tts">` for replies |
| `styles.css` | All design tokens in the `:root` block; components use only those variables |
| `data.js` | `BRAND` (the only place the app name appears), formatters (`formatPaise`, `formatWhen`, …) and the API client: `TransactionRepository`, `AgentRepository`, `PendingPayments`, `DemoRepository`. All repository methods are async. |
| `voice.js` | Mic capture (`Voice.capture`: `getUserMedia` + `MediaRecorder`, voice level measured on the audio thread by a small AudioWorklet, end of speech after ~1.5 s silence, no-speech timeout) and the listening sheet (`Voice.listen`) |
| `app.js` | Components (render functions with a props comment, returning HTML strings), the screens and a hash router |

## Screens
| Route | Screen |
|---|---|
| `#/` | Home: recent payments, plus a demo "skip time +1 day" button |
| `#/history` | Full history; a badge on payments with a case update; mic for the most urgent open case |
| `#/txn/:id` | Transaction details (SUCCESS / FAILED / PENDING), case status line, **floating AI mic** on failed or pending payments |
| `#/agent/:txnId` | AI Resolve chat bound to that payment: pinned case card, bubbles, chips, mic (voice-first) and a text fallback, spoken replies, speaker mute |
| `#/pay/:caseId` | Pre-filled retry + mock PIN. Opens only from the backend's `OPEN_PAY_SCREEN` action |

## Rules
- Amounts are integer paise; format only for display.
- The backend decides. The UI never infers "safe to retry" from `debited`; it shows `statusLine`, the reply, the chips and the actions.
- Escape every dynamic string with `esc()`. Chat text is user input.
- The API contract is in `docs/API_CONTRACT.md`.

## Voice
- **Mic tap on a payment:** the listening sheet rises over that screen. It records until ~1.5 s of silence (or a tap on the orb), then opens the chat for that payment and sends the audio to `POST /v1/voice/turn`. The backend does Sarvam STT, so no key lives in the browser.
- **Hands-free conversation (Siri-style):** one tap starts a conversation. After each spoken reply the app listens again by itself, and a voice bar ("Listening… / Thinking… / Speaking…", live words, keyboard, ✕) replaces the text box.
  - **It ends when:** the user is silent for `VOICE.noSpeechMs` (20 s), says thanks or goodbye, asks for a human, taps ✕ or the keyboard, the pay screen opens, or the user leaves the chat.
  - **"Didn't catch that" (noise, no words):** it keeps listening. It only pauses after `VOICE.maxMisses` (3) misses in a row.
  - **Pauses mid-sentence:** up to `VOICE.silenceMs` (2 s) is fine; one turn can run up to 30 s.
  - **Room noise** is measured in the first 0.4 s of each listen, and speech must be `VOICE.noiseFactor` (3×) louder, so fans or the agent's own voice tail don't count as speech.
  - **While listening,** the user's words appear in the chat as they speak (browser preview); Sarvam's transcript replaces them.
  - **Tapping the orb:** while it's speaking, this interrupts (barge-in); while it's listening, this sends right away.
  - **To go back to one tap per question,** set `VOICE.handsFree = false`.
- **Replies:** the text is revealed word by word in step with the voice (`playAudio` progress), and the follow-up chips appear only after the reply finishes. When muted, or if the audio can't play, the text types out at `VOICE.wordMs` per word. If the audio never starts loading, it gives up after 8 s and types the text instead.
- **Live transcript in the sheet:** a preview from the browser's own speech recognizer, where one exists. In Chrome that audio is processed by Google. Only Sarvam's transcript is used. Turn the preview off with `VOICE.liveTranscript` in `data.js`.
- **Mic access:** browsers allow the mic only on `localhost` or HTTPS. For a phone, use an HTTPS tunnel and set `PUBLIC_BASE_URL` in `backend/.env` to that address.
- **Fallbacks:** when the server has voice off (`/healthz`), the browser can't record, or mic permission is denied, the chat works by typing.
