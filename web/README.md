# web/: demo UI (prototype)

A phone-width web app for the AI Resolve feature. Plain HTML, CSS and JS: no framework, no CDN, no build step. FastAPI serves this folder at `/`, so open **http://localhost:8000/** (same origin as the API, no CORS).

`Paytm-Clone-main/` is Sahil's original Paytm-style site. It stays untouched; its colours (`#00baf2`, `#002970`, `#f5f7fa`) are the design tokens here. It's still served at `/Paytm-Clone-main/`.

## Files
| File | What |
|---|---|
| `index.html` | Shell: `#app` root, hidden `<audio id="tts">` for replies |
| `styles.css` | All design tokens in the `:root` block; components use only those variables |
| `data.js` | `BRAND` (the only place the app name appears), formatters (`formatPaise`, `formatWhen`, …) and the API client: `TransactionRepository`, `AgentRepository`, `PendingPayments`, `DemoRepository`. All repository methods are async. |
| `app.js` | Components (render functions with a props comment, returning HTML strings), the screens and a hash router |

## Screens
| Route | Screen |
|---|---|
| `#/` | Home: recent payments, plus a demo "skip time +1 day" button |
| `#/history` | Full history; a badge on payments with a case update; mic for the most urgent open case |
| `#/txn/:id` | Transaction details (SUCCESS / FAILED / PENDING), case status line, **floating AI mic** on failed or pending payments |
| `#/agent/:txnId` | AI Resolve chat bound to that payment: pinned case card, bubbles, chips, text input (voice comes in build step 7) |
| `#/pay/:caseId` | Pre-filled retry + mock PIN. Opens only from the backend's `OPEN_PAY_SCREEN` action |

## Rules
- Amounts are integer paise; format only for display.
- The backend decides. The UI never infers "safe to retry" from `debited`; it shows `statusLine`, the reply, the chips and the actions.
- Escape every dynamic string with `esc()`. Chat text is user input.
- The API contract is in `docs/API_CONTRACT.md`.
