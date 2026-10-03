"""The app's UI language for the current request.

The web app sends `X-UI-Lang: en | hi | mr` on every /v1 call (the language toggle). The agent then
answers in that language, and status lines / next actions / failure reasons come back in it.
Without the header (other clients, tests) nothing is forced: replies follow the detected language
and labels stay English, as before.
"""
from contextvars import ContextVar

LANGS = ("en", "hi", "mr")
_ui_lang: ContextVar[str | None] = ContextVar("ui_lang", default=None)


def parse(value: str | None) -> str | None:
    v = (value or "").strip().lower()[:2]
    return v if v in LANGS else None


def set_ui_lang(value: str | None):
    return _ui_lang.set(parse(value))


def reset_ui_lang(token) -> None:
    _ui_lang.reset(token)


def ui_lang() -> str | None:
    """The language the user chose in the app, or None when the client didn't say."""
    return _ui_lang.get()


def label_lang() -> str:
    """Language for labels (status lines etc.): the UI language, else English."""
    return _ui_lang.get() or "en"
