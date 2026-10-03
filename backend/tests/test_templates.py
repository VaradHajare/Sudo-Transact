from datetime import datetime

import pytest

from app.conversation import templates as T
from app.conversation.format import day_month, inr

FACTS = T.Facts(amount_paise=149900, payee="City Mobiles", expected_by=datetime(2026, 10, 4, 18, 29, 59))


def test_inr_grouping():
    assert inr(35000) == "350"
    assert inr(149900) == "1,499"
    assert inr(12345678) == "1,23,456.78"
    assert inr(100) == "1"


def test_dates_per_language():
    d = datetime(2026, 10, 4, 18, 29, 59)  # 4 Oct 23:59 IST
    assert day_month(d, "en") == "4 October"
    assert day_month(d, "hi") == "4 अक्टूबर"
    assert day_month(d, "mr") == "4 ऑक्टोबर"


def test_s2_hindi_answer_matches_spec():
    text = T.status_text("DEBIT_WAIT", FACTS, "hi")
    assert text == ("हाँ, आपके खाते से 1,499 रुपये कटे हैं, लेकिन City Mobiles को नहीं पहुंचे। "
                    "दोबारा पेमेंट मत कीजिए। यह पैसा 4 अक्टूबर तक अपने आप वापस आना चाहिए।")


@pytest.mark.parametrize("lang", T.LANGS)
def test_every_template_fills_and_passes_number_check(lang):
    facts = FACTS.model_copy(update={"dispute_ref": "UDIR1A2B3C4D", "compensation_paise": 20000, "days_late": 2,
                                     "reversed_at": datetime(2026, 10, 3, 6, 0)})
    texts = [T.status_text(s, facts, lang) for s in T.STATUS[lang]]
    texts += [T.why_text(s, facts, lang) for s in T.STATUS[lang]]
    texts += [T.dispute_request_text(s, facts, lang) for s in T.STATUS[lang]]
    texts += [T.retry_text(k, facts, lang) for k in T.RETRY[lang]]
    texts += [T.what_if_text("DEBIT_WAIT", facts, lang)]
    for t in texts:
        assert "{" not in t
        assert T.number_check(t, [facts], lang) == [], t


def test_number_check_catches_invented_numbers():
    assert T.number_check("₹1,500 will come back by 9 October", [FACTS], "en") == ["1500", "9"]


def test_retry_chip_label():
    chips = T.chips("RETRY_OFFER", T.Facts(amount_paise=35000, payee="Sharma Medicals"), "en")
    assert chips[0] == {"id": "retry", "label": "Pay ₹350 again"}
