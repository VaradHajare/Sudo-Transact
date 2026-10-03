"""Short-lived session tokens (HMAC-signed). The app holds no API keys; it only holds this token.

Demo only: POST /v1/session issues a token for a known user id without a password (DEMO_MODE).
"""
import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import get_app_settings, get_db
from app.models import User


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user_id: str, settings: Settings) -> tuple[str, int]:
    exp = int(time.time()) + settings.SESSION_TOKEN_TTL_SECONDS
    body = _b64(json.dumps({"uid": user_id, "exp": exp}).encode())
    sig = _b64(hmac.new(settings.SESSION_TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", exp


def verify_token(token: str, settings: Settings) -> str | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(settings.SESSION_TOKEN_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(_unb64(body))
        return data["uid"] if data["exp"] > time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db),
                 settings: Settings = Depends(get_app_settings)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    uid = verify_token(authorization[7:].strip(), settings)
    user = db.get(User, uid) if uid else None
    if user is None:
        raise HTTPException(401, "invalid or expired token")
    return user
