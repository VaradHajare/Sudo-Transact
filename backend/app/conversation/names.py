"""Payee names in the UI / reply language (Devanagari for Hindi and Marathi).

Deterministic: a reviewed word dictionary, not the LLM (it may only do the four jobs in CLAUDE.md).
A name is shown in Devanagari only when every word is known; otherwise the original name is kept,
because a half-translated or guessed name is worse than an English one. Payment payloads, UPI IDs
and stored records always keep the original name.

Native-speaker review needed, like the reply templates.
"""
import re

# word -> (Hindi, Marathi)
WORDS = {
    "sharma": ("शर्मा", "शर्मा"), "medicals": ("मेडिकल्स", "मेडिकल्स"), "medical": ("मेडिकल", "मेडिकल"),
    "city": ("सिटी", "सिटी"), "mobiles": ("मोबाइल्स", "मोबाईल्स"), "mobile": ("मोबाइल", "मोबाईल"),
    "gupta": ("गुप्ता", "गुप्ता"), "stores": ("स्टोर्स", "स्टोअर्स"), "store": ("स्टोर", "स्टोअर"),
    "patel": ("पटेल", "पटेल"), "electronics": ("इलेक्ट्रॉनिक्स", "इलेक्ट्रॉनिक्स"),
    "ramesh": ("रमेश", "रमेश"), "tea": ("टी", "टी"), "stall": ("स्टॉल", "स्टॉल"),
    "anil": ("अनिल", "अनिल"), "kumar": ("कुमार", "कुमार"), "swiggy": ("स्विगी", "स्विगी"),
    "mahesh": ("महेश", "महेश"), "kirana": ("किराना", "किराणा"), "jio": ("जियो", "जिओ"),
    "prepaid": ("प्रीपेड", "प्रीपेड"), "recharge": ("रिचार्ज", "रिचार्ज"), "rahul": ("राहुल", "राहुल"),
    "msedcl": ("एमएसईडीसीएल", "महावितरण"), "electricity": ("बिजली", "वीज"),
    "kaveri": ("कावेरी", "कावेरी"), "restaurant": ("रेस्टोरेंट", "रेस्टॉरंट"), "om": ("ओम", "ओम"),
    "sweets": ("स्वीट्स", "स्वीट्स"), "sai": ("साई", "साई"), "hardware": ("हार्डवेयर", "हार्डवेअर"),
    "priya": ("प्रिया", "प्रिया"), "fashion": ("फ़ैशन", "फॅशन"),
}
_COL = {"hi": 0, "mr": 1}
_WORD = re.compile(r"[A-Za-z]+")


def local_name(name: str | None, lang: str | None) -> str | None:
    """'Kaveri Restaurant' -> 'कावेरी रेस्टोरेंट' (hi); unchanged for English or unknown words."""
    if not name or lang not in _COL:
        return name
    words = _WORD.findall(name)
    if not words or any(w.lower() not in WORDS for w in words):
        return name
    return _WORD.sub(lambda m: WORDS[m.group().lower()][_COL[lang]], name)
