"""Background scheduler (spec 6.7): one in-process worker polling the `jobs` table (no Redis).

Runs whether or not the app is open. Job kinds, all of which re-run the case pipeline (so the
rules decide, and the live re-check guards every action):
  RECHECK_CASE      pending / bank-down / 7b waits: look again
  SLA_DEADLINE      F4 deadline reached: dispute + compensation if the money is still not back
  DISPUTE_FOLLOWUP  after a dispute: catch a late reversal (close) or grow the compensation
  CASE_SUMMARY      LLM reviewer note for an escalated case file (only when the LLM is on)

Jobs are claimed with a conditional UPDATE (QUEUED -> RUNNING), so the worker thread and a
/mock/clock time-skip can never run the same job twice.
"""
import json
import logging
import threading
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app import clock, providers
from app.config import Settings
from app.conversation import llm_tasks
from app.engine import audit
from app.engine.pipeline import NOT_REDECIDED, process_transaction
from app.models import Case, Job

log = logging.getLogger("scheduler")
JOB_KINDS = {"RECHECK_CASE", "SLA_DEADLINE", "DISPUTE_FOLLOWUP", "CASE_SUMMARY"}
MAX_JOBS_PER_TICK = 200


def _claim_next(db: Session) -> int | None:
    now = clock.now(db)
    candidates = (db.query(Job.id).filter(Job.status == "QUEUED", Job.run_at <= now)
                  .order_by(Job.run_at, Job.id).limit(5).all())
    for (job_id,) in candidates:
        claimed = (db.query(Job).filter(Job.id == job_id, Job.status == "QUEUED")
                   .update({"status": "RUNNING", "attempts": Job.attempts + 1}, synchronize_session=False))
        db.commit()
        if claimed:
            return job_id
    return None


def run_job(db: Session, settings: Settings, job_id: int) -> dict:
    job = db.get(Job, job_id)
    db.refresh(job)
    case = db.get(Case, job.case_id) if job.case_id else None
    summary = {"job_id": job.id, "kind": job.kind, "case_id": job.case_id}
    try:
        if job.kind not in JOB_KINDS:
            raise ValueError(f"unknown job kind {job.kind}")
        if job.kind == "CASE_SUMMARY":
            summary.update(_write_case_summary(db, case))
            job.status = "DONE"
            db.commit()
            return summary
        if case is None or case.state in NOT_REDECIDED:
            job.status = "DONE"
            summary.update(status="SKIPPED", reason=f"case is {case.state if case else 'missing'}")
            db.commit()
            return summary
        before = case.state
        process_transaction(db, settings, case.txn_id, trigger=f"SCHEDULER:{job.kind}")
        now = clock.now(db)
        audit.log(db, case.id, now, "JOB_RUN", {"job_id": job.id, "kind": job.kind, "from": before,
                                                "to": case.state, "rule": case.rule_id}, actor="SCHEDULER")
        job.status = "DONE"
        db.commit()
        summary.update(status="DONE", txn_id=case.txn_id, **{"from": before}, to=case.state,
                       decision=case.decision, rule=case.rule_id)
        return summary
    except Exception as e:  # noqa: BLE001  (a failing job must not kill the worker)
        db.rollback()
        job = db.get(Job, job_id)
        job.last_error = f"{type(e).__name__}: {e}"[:500]
        if job.attempts >= settings.JOB_MAX_ATTEMPTS:
            job.status = "FAILED"
        else:
            job.status = "QUEUED"
            job.run_at = clock.now(db) + timedelta(seconds=settings.JOB_RETRY_DELAY_SECONDS)
        db.commit()
        log.exception("job %s (%s) failed", job_id, job.kind)
        summary.update(status=job.status, error=job.last_error)
        return summary


def _write_case_summary(db: Session, case: Case | None) -> dict:
    """LLM job 4: a short reviewer note added to the escalation case file."""
    p = providers.current()
    if case is None or not case.case_file_json or p.llm is None:
        return {"status": "SKIPPED", "reason": "no case file or LLM off"}
    case_file = json.loads(case.case_file_json)
    text, meta = llm_tasks.case_summary(p.llm, case_file)
    now = clock.now(db)
    audit.log(db, case.id, now, "LLM_CASE_SUMMARY", {"ok": meta.ok, "latency_ms": meta.latency_ms,
                                                      "error": meta.error}, actor="AGENT")
    if text is None:
        raise RuntimeError(meta.error or "LLM summary failed")  # retried with backoff
    case_file["llm_summary"] = text
    case_file["llm_reasoning"] = [json.loads(e.payload_json) for e in audit.events(db, case.id)
                                  if e.event_type == "LLM_CLASSIFIED"] or None
    case.case_file_json = json.dumps(case_file, ensure_ascii=False)
    return {"status": "DONE", "case_id": case.id}


def run_due_jobs(db: Session, settings: Settings) -> list[dict]:
    """Run every job that is due now. Used by the worker and right after a /mock/clock time-skip."""
    out = []
    for _ in range(MAX_JOBS_PER_TICK):
        job_id = _claim_next(db)
        if job_id is None:
            break
        out.append(run_job(db, settings, job_id))
    return out


def recover_stale_jobs(db: Session) -> int:
    """Jobs left RUNNING by a crash or restart go back to the queue."""
    n = db.query(Job).filter(Job.status == "RUNNING").update({"status": "QUEUED"}, synchronize_session=False)
    db.commit()
    return n


class Worker:
    def __init__(self, SessionLocal: sessionmaker, settings: Settings):
        self.SessionLocal = SessionLocal
        self.settings = settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ticks = 0

    def start(self) -> None:
        with self.SessionLocal() as db:
            n = recover_stale_jobs(db)
        if n:
            log.info("re-queued %d stale jobs", n)
        self._thread = threading.Thread(target=self._loop, name="jobs-worker", daemon=True)
        self._thread.start()
        log.info("scheduler started (poll every %ss)", self.settings.SCHEDULER_POLL_SECONDS)

    def _loop(self) -> None:
        while not self._stop.wait(self.settings.SCHEDULER_POLL_SECONDS):
            try:
                with self.SessionLocal() as db:
                    done = run_due_jobs(db, self.settings)
                for d in done:
                    log.info("job %s %s case=%s %s -> %s", d["job_id"], d["kind"], d.get("case_id"),
                             d.get("from"), d.get("to", d["status"]))
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick failed")
            self.ticks += 1

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
