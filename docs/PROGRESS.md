# Progress

## Done
- **Step 1: skeleton.** `backend/` FastAPI app; pydantic-settings config (`backend/.env`, `.env.example`); SQLite with WAL + busy timeout on every connection; all spec §7 tables + `jobs`, `messages`, `idempotency_keys`, mock-world tables; append-only `case_events` (DB triggers); simulated clock; demo seed (relative dates) and `scripts/reset_db.py`; FastAPI serves `web/` at `/`.

- **Step 2: mock world.** `PaymentSource` / `EvidenceSource` / `DisputeChannel` interfaces (`app/mock/sources.py`) with DB-backed mocks; `/mock/paytm/transactions`, `/mock/npci/status`, `/mock/bank/ledger`, `/mock/merchant/credit`, `/mock/npci/udir/dispute`, `/mock/clock` (time-skip), `/mock/inject`.

- **Step 3: engine.** `app/engine/`: evidence assembler with conflict / suspicious / settling detection; rules diagnosis F1-F10 (+AMBIGUOUS); decision rules 0-8 + 7b (`decision.py`, pure); safe-retry gate with 10 named checks (`retry_gate.py`); live re-check before OFFER_RETRY / RAISE_DISPUTE / CLOSE and before returning the pay-screen payload; actions (disputes via mock UDIR, compensation, escalation case file, jobs rows, NOTIFY messages); audit events for every step. Reply templates en/hi/mr + number-check (`app/conversation/templates.py`). Seeded cases are prepared at seed time. `/mock/clock` re-decides open cases (stand-in for the step-6 scheduler). Tests: every rule, every gate condition, every class, pipeline scenarios.

## Next
- Step 4: `/v1` API (spec section 9) and `docs/API_CONTRACT.md`.

## Notes / decisions
- Times are naive UTC in the DB; IST (+05:30) for display and SLA end-of-day.
- SLA deadline = end of day IST, T+n after the debit date (n from config).
- A user's "money was debited" statement is not treated as suspicious on its own (honest confusion is common); amount/payee mismatches and repeat claims are.
- Hindi/Marathi templates need a native speaker's review.
