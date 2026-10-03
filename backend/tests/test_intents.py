import pytest

from app.conversation.intents import detect_intent, detect_language, extract_amount_paise, redact


@pytest.mark.parametrize("text,lang", [
    ("paise kat gaye par mila nahi", "hi"),
    ("मेरा पेमेंट फेल हो गया, पैसे कटे क्या?", "hi"),
    ("Did my money get cut?", "en"),
    ("majhe paise kaple pan milale nahi", "mr"),
    ("माझे पैसे कापले गेले आहेत", "mr"),
    ("अगर नहीं आया तो?", "hi"),
])
def test_language(text, lang):
    assert detect_language(text, "en") == lang


def test_language_keeps_current_without_signal():
    assert detect_language("ok", "hi") == "hi"
    assert detect_language("1499", "mr") == "mr"


@pytest.mark.parametrize("text,state,intent", [
    ("paise kat gaye par mila nahi", "WAITING", "status_check"),
    ("Did my money get cut?", "RETRY_OFFERED", "status_check"),
    ("yes", "RETRY_OFFERED", "confirm_retry"),
    ("haan dobara bhejo", "RETRY_OFFERED", "confirm_retry"),
    ("हाँ", "RETRY_OFFERED", "confirm_retry"),
    ("no thanks", "RETRY_OFFERED", "decline_retry"),
    ("kya ho gaya?", "RETRY_OFFERED", "status_check"),
    ("yes", "WAITING", "status_check"),
    ("अगर नहीं आया तो?", "WAITING", "what_if"),
    ("what if it doesn't come back", "WAITING", "what_if"),
    ("why?", "WAITING", "why"),
    ("I want to talk to a human", "WAITING", "talk_to_human"),
    ("shikayat karo", "WAITING", "raise_dispute"),
    ("what should I do", "WAITING", "what_should_i_do"),
    ("please repeat", "WAITING", "repeat"),
    ("thank you", "WAITING", "goodbye"),
    ("ok thanks bye", "WAITING", "goodbye"),
    ("dhanyavad", "WAITING", "goodbye"),
    ("बहुत धन्यवाद", "WAITING", "goodbye"),
    ("ठीक आहे, आभारी आहे", "WAITING", "goodbye"),
    # hands-free safety: a polite sign-off must never be read as "yes, pay again"
    ("ok thanks", "RETRY_OFFERED", "goodbye"),
    ("no thanks", "RETRY_OFFERED", "decline_retry"),
    ("yes please", "RETRY_OFFERED", "confirm_retry"),
    # off-topic: told to stay on this transaction
    ("Can you give me the code for palindrome?", "RETRY_OFFERED", "off_topic"),
    ("what's the weather today", "WAITING", "off_topic"),
    ("aaj mausam kaisa hai", "WAITING", "off_topic"),
    ("मुझे एक चुटकुला सुनाओ", "WAITING", "off_topic"),
    ("मला एक विनोद सांगा", "WAITING", "off_topic"),
    ("nice weather, but where is my money?", "WAITING", "status_check"),  # mixed: payment wins
])
def test_intent(text, state, intent):
    assert detect_intent(text, state) == intent


def test_amount_claims():
    assert extract_amount_paise("I paid ₹1,499 to them") == 149900
    assert extract_amount_paise("5000 rupaye kat gaye") == 500000
    assert extract_amount_paise("paise kat gaye") is None


def test_redact_long_digits():
    assert redact("my account 123456789 and ref 42") == "my account [number] and ref 42"
