# Progress

## Done
- **Step 1: skeleton.** `backend/` FastAPI app; pydantic-settings config (`backend/.env`, `.env.example`); SQLite with WAL + busy timeout on every connection; all spec §7 tables + `jobs`, `messages`, `idempotency_keys`, mock-world tables; append-only `case_events` (DB triggers); simulated clock; demo seed (relative dates) and `scripts/reset_db.py`; FastAPI serves `web/` at `/`.

- **Step 2: mock world.** `PaymentSource` / `EvidenceSource` / `DisputeChannel` interfaces (`app/mock/sources.py`) with DB-backed mocks; `/mock/paytm/transactions`, `/mock/npci/status`, `/mock/bank/ledger`, `/mock/merchant/credit`, `/mock/npci/udir/dispute`, `/mock/clock` (time-skip), `/mock/inject`.

## Next
- Step 3: evidence assembler, diagnosis, decision engine, retry gate, live re-check, audit log (tests first).
