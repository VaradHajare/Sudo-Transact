"""Idempotency-Key support for mutating calls: the same key replays the stored response."""
import hashlib
import json
from collections.abc import Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import clock
from app.models import IdempotencyKey


def run_idempotent(db: Session, user_id: str, key: str | None, path: str, body: dict,
                   fn: Callable[[], tuple[int, dict]]) -> JSONResponse:
    """Run `fn` (which returns status, json) once per (user, key). Commits on success."""
    req_hash = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    if key:
        prev = (db.query(IdempotencyKey).filter(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
                .one_or_none())
        if prev:
            if prev.path != path or prev.request_hash != req_hash:
                raise HTTPException(422, "Idempotency-Key reused with a different request")
            return JSONResponse(json.loads(prev.response_json), status_code=prev.status_code,
                                headers={"Idempotent-Replay": "true"})
    status, payload = fn()
    if key and status < 500:
        db.add(IdempotencyKey(user_id=user_id, key=key, path=path, request_hash=req_hash, status_code=status,
                              response_json=json.dumps(payload, default=str, ensure_ascii=False),
                              created_at=clock.now(db)))
    db.commit()
    return JSONResponse(payload, status_code=status)
