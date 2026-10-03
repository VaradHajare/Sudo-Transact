"""Language + intent + claim extraction without an LLM (keyword rules for en / hi / mr, including
romanized Hindi and Marathi). The LLM adapter (build step 7) replaces this behind the same functions.

User text is untrusted: it only selects an intent from a fixed list and yields claims that are
compared with evidence. It never becomes an instruction.
"""
import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
TOKEN = re.compile(r"[\wऀ-ॿ']+", re.UNICODE)

HI_DEV = {"है", "हैं", "मेरा", "मेरे", "मेरी", "क्या", "नहीं", "हुआ", "गया", "गए", "गई", "कटे", "कटा", "कट",
          "मुझे", "आप", "वापस", "अगर", "मिला", "मिले", "क्यों", "दोबारा", "भेजो", "हाँ", "हां", "तो", "पर", "लेकिन"}
MR_DEV = {"आहे", "आहेत", "नाही", "माझे", "माझा", "माझी", "झाले", "झाला", "कापले", "कापला", "काय", "मला",
          "तुम्ही", "परत", "पुन्हा", "केले", "मिळाले", "मिळाला", "का", "तर", "पण", "हो", "नको", "पाठवा"}
HI_ROM = {"paise", "paisa", "kat", "kata", "kate", "katge", "gaye", "gaya", "gayi", "mila", "mile", "nahi",
          "nahin", "kya", "mera", "mere", "meri", "hua", "hai", "hain", "kyu", "kyon", "kyun", "wapas", "vapas",
          "agar", "kab", "haan", "dobara", "bhejo", "shikayat", "aaya", "aya", "karo", "mujhe", "aap", "par",
          "lekin", "abhi", "batao", "bataiye", "kitne", "rupaye", "rupay", "kaat"}
MR_ROM = {"majhe", "majha", "maze", "maza", "mazhe", "ahe", "aahe", "zhale", "jhale", "zala", "kaple",
          "kapla", "kapale", "kay", "parat", "kadhi", "mala", "tumhi", "pahije", "punha", "takrar", "milale",
          "milala", "nako", "pathva", "aale", "ala", "tar", "pan"}
SHARED_ROM = {"nahi", "paise", "paisa"}  # common to romanized Hindi and Marathi


def detect_language(text: str, current: str = "en") -> str:
    """Return en / hi / mr. Keeps `current` when the text carries no clear signal (e.g. "ok", "1")."""
    toks = [t.lower() for t in TOKEN.findall(text or "")]
    if not toks:
        return current
    if DEVANAGARI.search(text):
        hi = sum(t in HI_DEV for t in toks)
        mr = sum(t in MR_DEV for t in toks)
        return "mr" if mr > hi else "hi"
    hi = sum(t in HI_ROM for t in toks)
    mr = sum(t in MR_ROM for t in toks)
    mr_only = sum(t in MR_ROM and t not in SHARED_ROM for t in toks)
    hi_only = sum(t in HI_ROM and t not in SHARED_ROM for t in toks)
    if hi + mr == 0:
        ascii_words = [t for t in toks if t.isalpha()]
        return "en" if len(ascii_words) >= 2 else current
    if mr_only > hi_only:
        return "mr"
    if hi_only > 0 or hi >= 2:
        return "hi"
    return current if current in ("hi", "mr") else "hi"


INTENTS = ("status_check", "what_should_i_do", "why", "confirm_retry", "decline_retry", "raise_dispute",
           "repeat", "talk_to_human", "what_if")

_PATTERNS: list[tuple[str, list[str]]] = [
    ("talk_to_human", ["human", "person", "real agent", "customer care", "call me", "insaan", "insan", "aadmi",
                       "इंसान", "व्यक्ति", "बात करनी", "बात करवा", "माणूस", "माणसा", "manus", "manasa"]),
    ("repeat", ["repeat", "say that again", "say again", "phir se", "fir se", "dobara bolo", "फिर से",
                "पुन्हा सांगा", "punha sanga", "parat sanga"]),
    ("raise_dispute", ["complaint", "complain", "dispute", "shikayat", "शिकायत", "takrar", "तक्रार"]),
    ("what_if", ["what if", "if it doesn't", "if it does not", "if not", "what happens if", "agar nahi",
                 "agar na", "nahi aaya to", "nahi aya to", "अगर नहीं", "अगर न", "नहीं आया तो", "नाही आले तर",
                 "आले नाही तर", "nahi aale tar", "ale nahi tar", "parat nahi"]),
    ("why", ["why", "reason", "kyu", "kyon", "kyun", "क्यों", "क्यूँ", "कारण", "kaaran", "karan", "का झाले",
             "ka zhale", "ka jhale"]),
    ("what_should_i_do", ["what should i do", "what do i do", "what now", "what can i do", "kya karu",
                          "kya karun", "kya karna", "क्या करूँ", "क्या करूं", "क्या करें", "kay karu",
                          "kay karaycha", "काय करू", "काय करायचं"]),
]
_DECLINE = ["no", "nope", "don't", "dont", "do not", "not now", "cancel", "nahi", "nahin", "mat", "nako",
            "नहीं", "नही", "मत", "नको", "नाही"]
_CONFIRM = ["yes", "yeah", "yep", "yup", "ok", "okay", "sure", "pay again", "pay", "retry", "try again",
            "haan", "han", "ha", "ji", "theek", "thik", "bhejo", "dobara", "ho", "hoy", "chalel", "pathva",
            "हाँ", "हां", "जी", "ठीक", "भेजो", "भेजें", "हो", "चालेल", "पाठवा"]


def _has(text: str, phrase: str) -> bool:
    if DEVANAGARI.search(phrase):
        return phrase in text
    return re.search(rf"(?<![a-z']){re.escape(phrase)}(?![a-z'])", text) is not None


_QUESTION_WORDS = {"what", "did", "does", "is", "was", "how", "kya", "kaise", "kab", "kay", "kasa", "kuthe",
                   "क्या", "कैसे", "कब", "काय", "कसे", "कधी"}


def _is_question(t: str, toks: list[str]) -> bool:
    return "?" in t or any(tok in _QUESTION_WORDS for tok in toks)


def detect_intent(text: str, case_state: str | None = None) -> str:
    t = (text or "").lower().strip()
    if not t:
        return "status_check"
    for intent, phrases in _PATTERNS[:2]:  # human / repeat always win
        if any(_has(t, p) for p in phrases):
            return intent
    # Yes / no only mean something when a retry is on offer, and only in short non-question replies.
    toks = TOKEN.findall(t)
    if case_state == "RETRY_OFFERED" and len(toks) <= 5 and not _is_question(t, toks):
        if any(_has(t, p) for p in _DECLINE):
            return "decline_retry"
        if any(_has(t, p) for p in _CONFIRM):
            return "confirm_retry"
    for intent, phrases in _PATTERNS[2:]:
        if any(_has(t, p) for p in phrases):
            return intent
    return "status_check"


_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr|rupees?|rupaye|rupay|रुपये|रुपए|रुपया|रुपयांचे|रुपये)\s*([\d][\d,]*(?:\.\d{1,2})?)"
    r"|([\d][\d,]*(?:\.\d{1,2})?)\s*(?:₹|rs\.?|inr|rupees?|rupaye|rupay|रुपये|रुपए|रुपया|रुपयांचे|रु)",
    re.IGNORECASE)


def extract_amount_paise(text: str) -> int | None:
    m = _AMOUNT.search(text or "")
    if not m:
        return None
    raw = (m.group(1) or m.group(2)).replace(",", "")
    try:
        return round(float(raw) * 100)
    except ValueError:
        return None


_LONG_DIGITS = re.compile(r"\d{6,}")


def redact(text: str) -> str:
    """Transcripts are stored without long digit sequences (account numbers, refs, OTPs)."""
    return _LONG_DIGITS.sub("[number]", text or "")
