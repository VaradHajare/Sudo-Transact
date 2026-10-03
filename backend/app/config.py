"""Single settings module. Every threshold and switch comes from backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # app / session
    APP_ENV: str = "dev"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    SESSION_TOKEN_SECRET: str = "dev-only-change-me"
    SESSION_TOKEN_TTL_SECONDS: int = 86400
    # Prefix for reply-audio links. Empty = relative links (/v1/audio/...), which work through any
    # host or tunnel (phone demo). Set it only for a client on another origin that needs absolute URLs.
    PUBLIC_BASE_URL: str = ""
    DEMO_MODE: bool = True
    SEED_DEMO_DATA: bool = True
    # Demo: a payment made from Scan & Pay fails on purpose, and the agent offers help at once.
    # debited (money taken, not credited: F4) | declined (F1) | bank_down (F6) | pending (F3) | off
    DEMO_SCAN_PAY_FAILURE: str = "debited"
    DEMO_USER_ID: str = "u_demo"
    WEB_DIR: str = str(REPO_DIR / "web")

    # database (SQLite only; see CLAUDE.md)
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'sudo_transact.db').as_posix()}"
    SQLITE_BUSY_TIMEOUT_MS: int = 5000

    # LLM (off by default; templates are used when off)
    LLM_ENABLED: bool = False
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = "deepseek-flash"
    LLM_API_KEY: str = ""
    LLM_JSON_MODE: bool = False
    LLM_TIMEOUT_SECONDS: float = 10.0
    LLM_MAX_TOKENS: int = 2000  # includes hidden reasoning tokens on reasoning models
    LLM_MIN_CONFIDENCE: float = 0.7
    # Which of the four allowed LLM jobs are on (only when LLM_ENABLED). Rephrase is off by default:
    # it adds ~2 s per reply and the templates are already the reviewed wording.
    LLM_INTENT_ENABLED: bool = True  # only asked when the keyword rules find no intent
    LLM_CLASSIFY_ENABLED: bool = True  # AMBIGUOUS cases -> JSON class; low confidence escalates
    LLM_CASE_SUMMARY_ENABLED: bool = True  # escalation case-file summary (background job)
    LLM_REPHRASE_ENABLED: bool = False  # rephrase template replies; number-checked

    # Sarvam STT / TTS (off by default; text only when off)
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    SARVAM_TTS_SPEAKER: str = "shubh"
    STT_ENABLED: bool = False
    TTS_ENABLED: bool = False
    STT_MAX_AUDIO_BYTES: int = 10 * 1024 * 1024
    MEDIA_DIR: str = str(BACKEND_DIR / "media")  # synthesized reply audio (not user audio)

    # decision rules (spec 8.2 rules config)
    COMPENSATION_PER_DAY: int = 100  # rupees per day late
    SLA_BENEFICIARY_CREDIT_FAILURE_DAYS: int = 1  # T+1
    SLA_MERCHANT_CONFIRMATION_MISSING_DAYS: int = 5  # T+5
    PENDING_WINDOW_MINUTES: int = 30
    RETRY_COOLDOWN_SECONDS: int = 600
    MAX_RETRIES_PER_TXN: int = 1
    EVIDENCE_LAG_SECONDS: int = 120  # sources may disagree for this long without it being a conflict
    RECHECK_INTERVAL_MINUTES: int = 15  # next check for WAIT decisions
    REPEAT_CLAIM_THRESHOLD: int = 3  # claims in the window that make a user look suspicious
    REPEAT_CLAIM_WINDOW_DAYS: int = 30

    # background scheduler (jobs table, one in-process worker)
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_POLL_SECONDS: float = 2.0
    JOB_MAX_ATTEMPTS: int = 3
    JOB_RETRY_DELAY_SECONDS: int = 60
    DISPUTE_FOLLOWUP_HOURS: int = 24

    @field_validator("DATABASE_URL")
    @classmethod
    def sqlite_only(cls, v: str) -> str:
        if not v.startswith("sqlite"):
            raise ValueError("DATABASE_URL must be a sqlite URL (team decision: no Postgres)")
        # Resolve relative sqlite paths against backend/, not the current directory.
        prefix = "sqlite:///"
        if v.startswith(prefix) and v != "sqlite:///:memory:":
            path = Path(v[len(prefix):])
            if not path.is_absolute():
                v = prefix + (BACKEND_DIR / path).resolve().as_posix()
        return v

    @field_validator("MEDIA_DIR")
    @classmethod
    def media_dir_absolute(cls, v: str) -> str:
        p = Path(v)
        return str(p if p.is_absolute() else (BACKEND_DIR / p).resolve())

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite:///"
        if self.DATABASE_URL.startswith(prefix) and ":memory:" not in self.DATABASE_URL:
            return Path(self.DATABASE_URL[len(prefix):])
        return None

    @property
    def compensation_per_day_paise(self) -> int:
        return self.COMPENSATION_PER_DAY * 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
