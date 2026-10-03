"""Number and date formatting for replies. Facts are always formatted here, never by an LLM."""
from datetime import datetime

from app import clock

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
           "नवंबर", "दिसंबर"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर",
           "नोव्हेंबर", "डिसेंबर"],
}


def inr(paise: int) -> str:
    """Indian digit grouping without the symbol: 149900 -> '1,499'; 12345678 -> '1,23,456.78'."""
    rupees, p = divmod(abs(int(paise)), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    out = s if p == 0 else f"{s}.{p:02d}"
    return ("-" if paise < 0 else "") + out


def day_month(dt_utc: datetime | None, lang: str) -> str:
    if dt_utc is None:
        return ""
    d = clock.to_ist(dt_utc)
    return f"{d.day} {MONTHS.get(lang, MONTHS['en'])[d.month - 1]}"
