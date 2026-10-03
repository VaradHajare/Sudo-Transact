"""Reply templates in English, Hindi and Marathi. Facts (amounts, dates, references) are filled in
from the decision engine's output only; `number_check` verifies the final text.

Hindi and Marathi wording needs a native speaker's review before the demo (spec 10.5).
"""
import re
from datetime import datetime

from pydantic import BaseModel

from app.conversation.format import day_month, inr
from app.domain import CaseClass as C

LANGS = ("en", "hi", "mr")


class Facts(BaseModel):
    amount_paise: int
    payee: str
    expected_by: datetime | None = None
    dispute_ref: str | None = None
    compensation_paise: int | None = None
    days_late: int | None = None
    reversed_at: datetime | None = None

    def vars(self, lang: str) -> dict:
        return {
            "amount": inr(self.amount_paise), "payee": self.payee,
            "date": day_month(self.expected_by, lang), "rdate": day_month(self.reversed_at, lang),
            "ref": self.dispute_ref or "", "comp": inr(self.compensation_paise or 0),
            "days": str(self.days_late or 0),
        }


def situation(case_class: str | None, action: str | None, state: str, escalation_reason: str | None = None) -> str:
    """Map the engine's view of a case to one conversational situation."""
    if state == "RESOLVED":
        return "RESOLVED_BY_RETRY"
    if state == "ESCALATED":
        return "ESCALATED_USER" if escalation_reason == "USER_REQUESTED" else "ESCALATED"
    if state == "REVIEWED":
        return "REVIEWED"
    if case_class in (C.F1_DECLINED_PRE_DEBIT, C.F2_TIMEOUT_PRE_DEBIT):
        return "RETRY_OFFER" if action == "OFFER_RETRY" else "PRE_DEBIT_WAIT"
    return {
        C.F3_PENDING: "PENDING", C.F6_BANK_DOWNTIME: "BANK_DOWN",
        C.F4_DEBIT_NO_CREDIT: "DISPUTED" if action == "RAISE_DISPUTE" else "DEBIT_WAIT",
        C.F7_DUPLICATE_DEBIT: "DUPLICATE_DISPUTED", C.F8_ALREADY_REVERSED: "REVERSED",
        C.F5_DEEMED_SUCCESS: "SUCCEEDED",
    }.get(case_class, "ESCALATED")


# ------------------------------------------------------------------ status answers (also "what should I do")
STATUS = {
    "en": {
        "RETRY_OFFER": "No. Your ₹{amount} payment to {payee} didn't go through, and no money was taken from your account. Would you like to pay again?",
        "PRE_DEBIT_WAIT": "Your ₹{amount} payment to {payee} didn't go through, and no money has been taken from your account. The bank hasn't confirmed the final status yet, so please don't pay again just now. I'll check again shortly.",
        "PENDING": "Your ₹{amount} payment to {payee} is still being processed by the bank. No money has been taken so far. Please don't pay again yet; I'll keep checking.",
        "BANK_DOWN": "Your bank is having trouble right now, so your ₹{amount} payment to {payee} didn't go through. Your money is safe and was not taken. Please don't pay again now; try again a little later.",
        "DEBIT_WAIT": "Yes, ₹{amount} was taken from your account, but it did not reach {payee}. Please don't pay again. This money should come back to you automatically by {date}.",
        "DISPUTED": "Your ₹{amount} did not come back in time, so I have raised a complaint with the bank (reference {ref}). The bank also owes you ₹{comp} as compensation for the delay.",
        "DUPLICATE_DISPUTED": "₹{amount} was taken twice for your payment to {payee}. I have raised a complaint for the extra ₹{amount} (reference {ref}).",
        "REVERSED": "Good news: the ₹{amount} from your payment to {payee} came back to your account on {rdate}. You don't need to do anything.",
        "SUCCEEDED": "Your ₹{amount} payment to {payee} went through, and {payee} has received it. Please don't pay again.",
        "ESCALATED": "I can't safely decide this one on my own, because the bank's records and the payment records don't match. I've passed your case to a human expert with all the details, so you won't need to explain it again. Please don't pay again until we get back to you.",
        "ESCALATED_USER": "I've passed your case to a human expert with all the details, so you won't need to explain it again. They will get back to you here.",
        "REVIEWED": "A support specialist has reviewed your ₹{amount} payment to {payee}, and their answer is in this chat. Please don't pay again unless they ask you to.",
        "RESOLVED_BY_RETRY": "Your new payment of ₹{amount} to {payee} went through. This case is closed.",
    },
    "hi": {
        "RETRY_OFFER": "नहीं। {payee} को आपका {amount} रुपये का पेमेंट नहीं हुआ, और आपके खाते से कोई पैसा नहीं कटा। क्या आप दोबारा पेमेंट करना चाहेंगे?",
        "PRE_DEBIT_WAIT": "{payee} को आपका {amount} रुपये का पेमेंट नहीं हुआ, और आपके खाते से कोई पैसा नहीं कटा है। बैंक ने अभी अंतिम स्थिति नहीं बताई है, इसलिए अभी दोबारा पेमेंट मत कीजिए। मैं थोड़ी देर में फिर से जाँच करूँगा।",
        "PENDING": "{payee} को आपका {amount} रुपये का पेमेंट अभी बैंक में प्रोसेस हो रहा है। अभी तक कोई पैसा नहीं कटा है। अभी दोबारा पेमेंट मत कीजिए, मैं जाँच करता रहूँगा।",
        "BANK_DOWN": "आपके बैंक में अभी दिक्कत चल रही है, इसलिए {payee} को {amount} रुपये का पेमेंट नहीं हुआ। आपका पैसा सुरक्षित है और कटा नहीं है। अभी दोबारा पेमेंट मत कीजिए, थोड़ी देर बाद कोशिश कीजिए।",
        "DEBIT_WAIT": "हाँ, आपके खाते से {amount} रुपये कटे हैं, लेकिन {payee} को नहीं पहुंचे। दोबारा पेमेंट मत कीजिए। यह पैसा {date} तक अपने आप वापस आना चाहिए।",
        "DISPUTED": "आपके {amount} रुपये समय पर वापस नहीं आए, इसलिए मैंने शिकायत दर्ज कर दी है (रेफरेंस {ref})। बैंक को देरी के लिए {comp} रुपये हर्जाना भी देना होगा।",
        "DUPLICATE_DISPUTED": "{payee} के पेमेंट के लिए आपके खाते से {amount} रुपये दो बार कटे। मैंने ज़्यादा कटे {amount} रुपये के लिए शिकायत दर्ज कर दी है (रेफरेंस {ref})।",
        "REVERSED": "अच्छी खबर: {payee} वाले पेमेंट के {amount} रुपये {rdate} को आपके खाते में वापस आ चुके हैं। आपको कुछ करने की ज़रूरत नहीं है।",
        "SUCCEEDED": "{payee} को आपका {amount} रुपये का पेमेंट हो गया है, और उन्हें पैसे मिल गए हैं। दोबारा पेमेंट मत कीजिए।",
        "ESCALATED": "यह मामला मैं अपने आप तय नहीं कर सकता, क्योंकि बैंक और पेमेंट के रिकॉर्ड मेल नहीं खाते। मैंने आपका केस पूरी जानकारी के साथ एक विशेषज्ञ को भेज दिया है, आपको दोबारा कुछ बताने की ज़रूरत नहीं है। जब तक हम जवाब न दें, दोबारा पेमेंट मत कीजिए।",
        "ESCALATED_USER": "मैंने आपका केस पूरी जानकारी के साथ एक विशेषज्ञ को भेज दिया है, आपको दोबारा कुछ बताने की ज़रूरत नहीं है। वे यहीं आपको जवाब देंगे।",
        "REVIEWED": "एक सहायता विशेषज्ञ ने {payee} को किए गए आपके {amount} रुपये के पेमेंट की जाँच कर ली है, और उनका जवाब इसी चैट में है। जब तक वे न कहें, दोबारा पेमेंट मत कीजिए।",
        "RESOLVED_BY_RETRY": "{payee} को आपका नया {amount} रुपये का पेमेंट हो गया है। यह केस बंद हो गया है।",
    },
    "mr": {
        "RETRY_OFFER": "नाही. {payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट झाले नाही, आणि तुमच्या खात्यातून कोणतेही पैसे कापले गेले नाहीत. पुन्हा पेमेंट करायचे आहे का?",
        "PRE_DEBIT_WAIT": "{payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट झाले नाही, आणि तुमच्या खात्यातून कोणतेही पैसे कापले गेलेले नाहीत. बँकेने अजून अंतिम स्थिती सांगितलेली नाही, म्हणून आत्ता पुन्हा पेमेंट करू नका. मी थोड्या वेळाने पुन्हा तपासेन.",
        "PENDING": "{payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट अजून बँकेत प्रक्रियेत आहे. अजून कोणतेही पैसे कापले गेलेले नाहीत. आत्ता पुन्हा पेमेंट करू नका, मी तपासत राहीन.",
        "BANK_DOWN": "तुमच्या बँकेत सध्या अडचण आहे, म्हणून {payee} ला {amount} रुपयांचे पेमेंट झाले नाही. तुमचे पैसे सुरक्षित आहेत आणि कापले गेलेले नाहीत. आत्ता पुन्हा पेमेंट करू नका, थोड्या वेळाने प्रयत्न करा.",
        "DEBIT_WAIT": "हो, तुमच्या खात्यातून {amount} रुपये कापले गेले आहेत, पण ते {payee} ला पोहोचले नाहीत. पुन्हा पेमेंट करू नका. हे पैसे {date} पर्यंत आपोआप परत यायला हवेत.",
        "DISPUTED": "तुमचे {amount} रुपये वेळेत परत आले नाहीत, म्हणून मी तक्रार नोंदवली आहे (संदर्भ {ref}). उशिरासाठी बँकेला {comp} रुपये भरपाई देखील द्यावी लागेल.",
        "DUPLICATE_DISPUTED": "{payee} च्या पेमेंटसाठी तुमच्या खात्यातून {amount} रुपये दोनदा कापले गेले. जास्तीच्या {amount} रुपयांसाठी मी तक्रार नोंदवली आहे (संदर्भ {ref}).",
        "REVERSED": "चांगली बातमी: {payee} च्या पेमेंटचे {amount} रुपये {rdate} रोजी तुमच्या खात्यात परत आले आहेत. तुम्हाला काहीही करण्याची गरज नाही.",
        "SUCCEEDED": "{payee} ला तुमचे {amount} रुपयांचे पेमेंट झाले आहे, आणि त्यांना पैसे मिळाले आहेत. पुन्हा पेमेंट करू नका.",
        "ESCALATED": "हे प्रकरण मी स्वतः ठरवू शकत नाही, कारण बँकेचे आणि पेमेंटचे रेकॉर्ड जुळत नाहीत. मी तुमचे प्रकरण संपूर्ण माहितीसह एका तज्ञाकडे पाठवले आहे, तुम्हाला पुन्हा काही सांगावे लागणार नाही. आम्ही उत्तर देईपर्यंत पुन्हा पेमेंट करू नका.",
        "ESCALATED_USER": "मी तुमचे प्रकरण संपूर्ण माहितीसह एका तज्ञाकडे पाठवले आहे, तुम्हाला पुन्हा काही सांगावे लागणार नाही. ते इथेच तुम्हाला उत्तर देतील.",
        "REVIEWED": "एका सहाय्यता तज्ञाने {payee} ला केलेल्या तुमच्या {amount} रुपयांच्या पेमेंटची तपासणी केली आहे, आणि त्यांचे उत्तर याच चॅटमध्ये आहे. त्यांनी सांगितल्याशिवाय पुन्हा पेमेंट करू नका.",
        "RESOLVED_BY_RETRY": "{payee} ला तुमचे नवीन {amount} रुपयांचे पेमेंट झाले आहे. हे प्रकरण बंद झाले आहे.",
    },
}

# ------------------------------------------------------------------ "why?"
_WHY_KEYS = {"RETRY_OFFER": "PRE_DEBIT", "PRE_DEBIT_WAIT": "PRE_DEBIT", "DUPLICATE_DISPUTED": "DUPLICATE",
             "ESCALATED_USER": "ESCALATED", "REVIEWED": "ESCALATED", "RESOLVED_BY_RETRY": "SUCCEEDED"}
WHY = {
    "en": {
        "PRE_DEBIT": "The payment stopped before any money left your account. The bank confirms there was no debit.",
        "PENDING": "The bank hasn't sent the final answer for this payment yet. That usually comes within a few hours.",
        "BANK_DOWN": "Your bank's server is not responding right now. This is not a problem with your account.",
        "DEBIT_WAIT": "The money left your bank, but {payee}'s bank couldn't accept it. In this situation the bank sends the money back automatically, by {date} at the latest.",
        "DISPUTED": "The bank had to return your money by {date} and didn't, so the rules allow a complaint and compensation.",
        "DUPLICATE": "The bank debited the same payment twice by mistake. Only one payment reached {payee}.",
        "REVERSED": "The payment couldn't be completed, so the bank sent the money back.",
        "SUCCEEDED": "The bank confirmed the payment after a short delay.",
        "ESCALATED": "The records from the bank and the payment network don't agree, so an automatic answer could be wrong.",
    },
    "hi": {
        "PRE_DEBIT": "पेमेंट आपके खाते से पैसा निकलने से पहले ही रुक गया। बैंक के अनुसार कोई पैसा नहीं कटा।",
        "PENDING": "बैंक ने इस पेमेंट का अंतिम जवाब अभी नहीं भेजा है। यह आम तौर पर कुछ घंटों में आ जाता है।",
        "BANK_DOWN": "आपके बैंक का सर्वर अभी जवाब नहीं दे रहा है। यह आपके खाते की समस्या नहीं है।",
        "DEBIT_WAIT": "पैसा आपके बैंक से निकल गया, लेकिन {payee} का बैंक उसे ले नहीं पाया। ऐसे में बैंक पैसा अपने आप वापस भेजता है, ज़्यादा से ज़्यादा {date} तक।",
        "DISPUTED": "बैंक को {date} तक आपका पैसा लौटाना था, लेकिन नहीं लौटाया। इसलिए नियमों के अनुसार शिकायत और हर्जाना बनता है।",
        "DUPLICATE": "बैंक ने गलती से एक ही पेमेंट दो बार काट लिया। {payee} तक सिर्फ़ एक पेमेंट पहुंचा।",
        "REVERSED": "पेमेंट पूरा नहीं हो सका, इसलिए बैंक ने पैसा वापस भेज दिया।",
        "SUCCEEDED": "बैंक ने थोड़ी देर बाद पेमेंट की पुष्टि कर दी।",
        "ESCALATED": "बैंक और पेमेंट नेटवर्क के रिकॉर्ड आपस में मेल नहीं खाते, इसलिए अपने आप दिया गया जवाब गलत हो सकता है।",
    },
    "mr": {
        "PRE_DEBIT": "तुमच्या खात्यातून पैसे जाण्याआधीच पेमेंट थांबले. बँकेनुसार कोणतेही पैसे कापले गेले नाहीत.",
        "PENDING": "बँकेने या पेमेंटचे अंतिम उत्तर अजून पाठवलेले नाही. ते सहसा काही तासांत येते.",
        "BANK_DOWN": "तुमच्या बँकेचा सर्व्हर सध्या प्रतिसाद देत नाही. ही तुमच्या खात्याची समस्या नाही.",
        "DEBIT_WAIT": "पैसे तुमच्या बँकेतून गेले, पण {payee} ची बँक ते स्वीकारू शकली नाही. अशा वेळी बँक पैसे आपोआप परत पाठवते, जास्तीत जास्त {date} पर्यंत.",
        "DISPUTED": "बँकेने {date} पर्यंत तुमचे पैसे परत करायला हवे होते, पण केले नाहीत. म्हणून नियमांनुसार तक्रार आणि भरपाई लागू होते.",
        "DUPLICATE": "बँकेने चुकून एकच पेमेंट दोनदा कापले. {payee} पर्यंत फक्त एकच पेमेंट पोहोचले.",
        "REVERSED": "पेमेंट पूर्ण होऊ शकले नाही, म्हणून बँकेने पैसे परत पाठवले.",
        "SUCCEEDED": "बँकेने थोड्या वेळाने पेमेंटची पुष्टी केली.",
        "ESCALATED": "बँक आणि पेमेंट नेटवर्कचे रेकॉर्ड जुळत नाहीत, म्हणून आपोआप दिलेले उत्तर चुकीचे असू शकते.",
    },
}

# ------------------------------------------------------------------ "what if it doesn't come back?" (F4 wait)
WHAT_IF = {
    "en": "If it isn't back by {date}, I'll raise a complaint automatically and tell you right here. You don't need to do anything.",
    "hi": "अगर {date} तक पैसा वापस नहीं आया, तो मैं अपने आप शिकायत दर्ज कर दूँगा, और यहीं आपको बता दूँगा।",
    "mr": "जर {date} पर्यंत पैसे परत आले नाहीत, तर मी आपोआप तक्रार नोंदवेन, आणि इथेच तुम्हाला सांगेन.",
}

# ------------------------------------------------------------------ user asks for a complaint
_DISPUTE_KEYS = {"DEBIT_WAIT": "TOO_EARLY", "DISPUTED": "ALREADY", "DUPLICATE_DISPUTED": "ALREADY",
                 "RETRY_OFFER": "NO_DEBIT", "PRE_DEBIT_WAIT": "NO_DEBIT", "BANK_DOWN": "NO_DEBIT",
                 "PENDING": "PENDING", "REVERSED": "REVERSED", "SUCCEEDED": "SUCCEEDED",
                 "RESOLVED_BY_RETRY": "SUCCEEDED", "ESCALATED": "ESCALATED", "ESCALATED_USER": "ESCALATED"}
DISPUTE_REQ = {
    "en": {
        "TOO_EARLY": "It's too early for a complaint: the bank has until {date} to return your money. If it isn't back by then, I'll raise the complaint automatically.",
        "ALREADY": "I've already raised a complaint (reference {ref}). I'll tell you here when there's an update.",
        "NO_DEBIT": "No money was taken from your account, so there is nothing to complain about.",
        "PENDING": "The payment is still being processed. If money gets taken and doesn't reach {payee}, I'll handle the complaint for you.",
        "REVERSED": "Your money has already come back, so there's nothing to complain about.",
        "SUCCEEDED": "{payee} has received your payment, so there's nothing to complain about.",
        "ESCALATED": "A human expert is already looking at your case.",
    },
    "hi": {
        "TOO_EARLY": "अभी शिकायत का समय नहीं हुआ है: बैंक के पास {date} तक पैसा लौटाने का समय है। अगर तब तक नहीं आया, तो मैं अपने आप शिकायत दर्ज कर दूँगा।",
        "ALREADY": "मैंने शिकायत पहले ही दर्ज कर दी है (रेफरेंस {ref})। कोई भी अपडेट आने पर मैं यहीं बताऊँगा।",
        "NO_DEBIT": "आपके खाते से कोई पैसा नहीं कटा है, इसलिए शिकायत की ज़रूरत नहीं है।",
        "PENDING": "पेमेंट अभी प्रोसेस हो रहा है। अगर पैसा कटा और {payee} को नहीं पहुंचा, तो शिकायत मैं संभाल लूँगा।",
        "REVERSED": "आपका पैसा वापस आ चुका है, इसलिए शिकायत की ज़रूरत नहीं है।",
        "SUCCEEDED": "{payee} को आपका पेमेंट मिल गया है, इसलिए शिकायत की ज़रूरत नहीं है।",
        "ESCALATED": "एक विशेषज्ञ पहले से आपका केस देख रहे हैं।",
    },
    "mr": {
        "TOO_EARLY": "तक्रारीची वेळ अजून आलेली नाही: बँकेकडे {date} पर्यंत पैसे परत करण्याची मुदत आहे. तोपर्यंत आले नाहीत, तर मी आपोआप तक्रार नोंदवेन.",
        "ALREADY": "मी आधीच तक्रार नोंदवली आहे (संदर्भ {ref}). काही अपडेट आल्यास मी इथेच सांगेन.",
        "NO_DEBIT": "तुमच्या खात्यातून कोणतेही पैसे कापले गेलेले नाहीत, म्हणून तक्रारीची गरज नाही.",
        "PENDING": "पेमेंट अजून प्रक्रियेत आहे. जर पैसे कापले गेले आणि {payee} ला पोहोचले नाहीत, तर तक्रार मी हाताळेन.",
        "REVERSED": "तुमचे पैसे परत आले आहेत, म्हणून तक्रारीची गरज नाही.",
        "SUCCEEDED": "{payee} ला तुमचे पेमेंट मिळाले आहे, म्हणून तक्रारीची गरज नाही.",
        "ESCALATED": "एक तज्ञ आधीच तुमचे प्रकरण पाहत आहेत.",
    },
}

# ------------------------------------------------------------------ retry flow
RETRY = {
    "en": {
        "CONFIRMED": "Paying ₹{amount} to {payee}. Opening the payment screen. Check the details, then enter your PIN.",
        "BLOCKED": "Wait: the bank's status for this payment has just changed, so I won't open a new payment.",
        "UNAVAILABLE": "I can't open a new payment for this one right now.",
        "DECLINED": "Okay, I won't pay again. No money was taken for this payment.",
    },
    "hi": {
        "CONFIRMED": "{payee} को {amount} रुपये भेज रहे हैं। पेमेंट स्क्रीन खुल रही है। जानकारी जाँच लीजिए, फिर अपना PIN डालिए।",
        "BLOCKED": "रुकिए: इस पेमेंट की बैंक स्थिति अभी बदली है, इसलिए मैं नया पेमेंट नहीं खोलूँगा।",
        "UNAVAILABLE": "इस पेमेंट के लिए मैं अभी नया पेमेंट नहीं खोल सकता।",
        "DECLINED": "ठीक है, मैं दोबारा पेमेंट नहीं करूँगा। इस पेमेंट के लिए कोई पैसा नहीं कटा।",
    },
    "mr": {
        "CONFIRMED": "{payee} ला {amount} रुपये पाठवत आहोत. पेमेंट स्क्रीन उघडत आहे. माहिती तपासा, मग तुमचा PIN टाका.",
        "BLOCKED": "थांबा: या पेमेंटची बँकेतील स्थिती आत्ताच बदलली आहे, म्हणून मी नवीन पेमेंट उघडणार नाही.",
        "UNAVAILABLE": "या पेमेंटसाठी मी आत्ता नवीन पेमेंट उघडू शकत नाही.",
        "DECLINED": "ठीक आहे, मी पुन्हा पेमेंट करणार नाही. या पेमेंटसाठी कोणतेही पैसे कापले गेले नाहीत.",
    },
}

# ------------------------------------------------------------------ end of a hands-free conversation
GOODBYE = {
    "en": "You're welcome. I'll keep watching this payment and tell you here if anything changes.",
    "hi": "आपका स्वागत है। मैं इस पेमेंट पर नज़र रखूँगा, और कुछ भी बदला तो यहीं बताऊँगा।",
    "mr": "आपले स्वागत आहे. मी या पेमेंटवर लक्ष ठेवेन, आणि काही बदलले तर इथेच सांगेन.",
}


def goodbye_text(lang: str) -> str:
    return GOODBYE[_lang(lang)]


# ------------------------------------------------------------------ off-topic questions
OFF_TOPIC = {
    "en": "Please stay relevant to this transaction. I can only help with your ₹{amount} payment to {payee}: what happened, what to do next, or talking to a person.",
    "hi": "कृपया इसी लेन-देन से जुड़ी बात पूछिए। मैं सिर्फ़ {payee} को किए गए आपके {amount} रुपये के पेमेंट में मदद कर सकता हूँ: क्या हुआ, आगे क्या करना है, या किसी इंसान से बात करना।",
    "mr": "कृपया याच व्यवहाराशी संबंधित विचारा. मी फक्त {payee} ला केलेल्या तुमच्या {amount} रुपयांच्या पेमेंटबद्दल मदत करू शकतो: काय झाले, पुढे काय करायचे, किंवा माणसाशी बोलणे.",
}


def off_topic_text(facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(OFF_TOPIC[lang], facts, lang)


# ------------------------------------------------------------------ briefing: urgent updates on OTHER cases
# Only actions the agent took on the user's behalf (spec 4.2). Good news like a landed refund is
# shown by the history badge and that case's own chat, not appended to an unrelated answer.
BRIEFING = {
    "en": {"DISPUTED": "Also: I raised a complaint for your ₹{amount} payment to {payee}."},
    "hi": {"DISPUTED": "एक और बात: {payee} वाले {amount} रुपये के पेमेंट के लिए मैंने शिकायत दर्ज कर दी है।"},
    "mr": {"DISPUTED": "आणखी एक: {payee} च्या {amount} रुपयांच्या पेमेंटसाठी मी तक्रार नोंदवली आहे."},
}
_BRIEFING_KEYS = {"DISPUTED": "DISPUTED", "DUPLICATE_DISPUTED": "DISPUTED"}

# Situations that produce an agent "update" message in the chat when they happen in the background.
UPDATE_SITUATIONS = {"DISPUTED", "DUPLICATE_DISPUTED", "REVERSED", "SUCCEEDED", "RESOLVED_BY_RETRY"}

# ------------------------------------------------------------------ proactive offer (right after a payment fails)
# Team decision (mentor feedback, 2026-10-03): when a payment fails in front of the user, the agent
# speaks first and offers help, instead of waiting for a tap on the mic.
OFFER = {
    "en": {
        "FAILED": "Your ₹{amount} payment to {payee} didn't go through. Would you like me to check what happened to your money?",
        "PENDING": "Your ₹{amount} payment to {payee} is still pending. Would you like me to check what is happening with your money?",
    },
    "hi": {
        "FAILED": "{payee} को आपका {amount} रुपये का पेमेंट नहीं हो पाया। क्या मैं देखूँ कि आपके पैसे के साथ क्या हुआ?",
        "PENDING": "{payee} को आपका {amount} रुपये का पेमेंट अभी रुका हुआ है। क्या मैं देखूँ कि आपके पैसे के साथ क्या हो रहा है?",
    },
    "mr": {
        "FAILED": "{payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट झाले नाही. तुमच्या पैशांचे काय झाले ते मी पाहू का?",
        "PENDING": "{payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट अजून प्रलंबित आहे. तुमच्या पैशांचे काय होत आहे ते मी पाहू का?",
    },
}


def offer_text(txn_status: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(OFFER[lang]["PENDING" if txn_status == "PENDING" else "FAILED"], facts, lang)


def offer_chips(facts: Facts, lang: str) -> list[dict]:
    labels = CHIP_LABELS[_lang(lang)]
    return [{"id": i, "label": _fill(labels[i], facts, lang)} for i in ("help", "no_thanks")]


# ------------------------------------------------------------------ human reviewer's outcome (posted to the chat)
# The reviewer's own notes stay internal; the user gets a fixed, number-checked message.
REVIEW = {
    "en": {
        "APPROVE": "A support specialist has checked your ₹{amount} payment to {payee} and is taking it up with the bank. You don't need to do anything; I'll tell you here when there is news.",
        "REJECT": "A support specialist has checked your ₹{amount} payment to {payee} against the bank's records and could not confirm a problem, so no further action is being taken. If you have more details, such as your bank statement, tell me here.",
        "REQUEST_INFO": "A support specialist is looking at your ₹{amount} payment to {payee} and needs a little more information. Please tell me here what your bank statement shows for this payment.",
    },
    "hi": {
        "APPROVE": "एक सहायता विशेषज्ञ ने {payee} को किए गए आपके {amount} रुपये के पेमेंट की जाँच की है और वे इसे बैंक के साथ आगे बढ़ा रहे हैं। आपको कुछ नहीं करना है; कोई खबर होगी तो मैं यहीं बताऊँगा।",
        "REJECT": "एक सहायता विशेषज्ञ ने {payee} को किए गए आपके {amount} रुपये के पेमेंट को बैंक के रिकॉर्ड से मिलाया, लेकिन कोई समस्या पक्की नहीं हो पाई, इसलिए आगे कोई कार्रवाई नहीं की जा रही है। अगर आपके पास और जानकारी है, जैसे बैंक स्टेटमेंट, तो यहाँ बताइए।",
        "REQUEST_INFO": "एक सहायता विशेषज्ञ {payee} को किए गए आपके {amount} रुपये के पेमेंट को देख रहे हैं और उन्हें थोड़ी और जानकारी चाहिए। कृपया यहाँ बताइए कि आपके बैंक स्टेटमेंट में इस पेमेंट के लिए क्या दिख रहा है।",
    },
    "mr": {
        "APPROVE": "एका सहाय्यता तज्ञाने {payee} ला केलेल्या तुमच्या {amount} रुपयांच्या पेमेंटची तपासणी केली आहे आणि ते हे बँकेकडे पुढे नेत आहेत. तुम्हाला काहीही करायची गरज नाही; काही बातमी आली तर मी इथेच सांगेन.",
        "REJECT": "एका सहाय्यता तज्ञाने {payee} ला केलेल्या तुमच्या {amount} रुपयांच्या पेमेंटची बँकेच्या रेकॉर्डशी पडताळणी केली, पण कोणतीही समस्या निश्चित झाली नाही, म्हणून पुढे कोणतीही कारवाई केली जात नाही. तुमच्याकडे आणखी माहिती असेल, जसे बँक स्टेटमेंट, तर इथे सांगा.",
        "REQUEST_INFO": "एक सहाय्यता तज्ञ {payee} ला केलेल्या तुमच्या {amount} रुपयांच्या पेमेंटची तपासणी करत आहेत आणि त्यांना थोडी अधिक माहिती हवी आहे. कृपया या पेमेंटसाठी तुमच्या बँक स्टेटमेंटमध्ये काय दिसते ते इथे सांगा.",
    },
}


def review_text(decision: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(REVIEW[lang][decision], facts, lang)


# ------------------------------------------------------------------ chips
CHIP_LABELS = {
    "en": {"retry": "Pay ₹{amount} again", "talk_to_human": "Talk to a human", "why": "Why?",
           "what_if": "What if it doesn't come back?", "help": "Yes, please help", "no_thanks": "No, thanks"},
    "hi": {"retry": "₹{amount} दोबारा भेजें", "talk_to_human": "किसी इंसान से बात करें", "why": "क्यों?",
           "what_if": "अगर नहीं आया तो?", "help": "हाँ, मदद कीजिए", "no_thanks": "नहीं, धन्यवाद"},
    "mr": {"retry": "₹{amount} पुन्हा पाठवा", "talk_to_human": "माणसाशी बोला", "why": "का?",
           "what_if": "परत नाही आले तर?", "help": "हो, मदत करा", "no_thanks": "नाही, धन्यवाद"},
}

# Short English status line for the case card / transaction details screen.
STATUS_LINE = {
    "RETRY_OFFER": "No money taken · safe to pay again",
    "PRE_DEBIT_WAIT": "No money taken · waiting for the bank's final status",
    "PENDING": "Processing · don't pay again yet",
    "BANK_DOWN": "Bank is down · your money is safe",
    "DEBIT_WAIT": "Money should return by {date}",
    "DISPUTED": "Complaint raised · ₹{comp} compensation flagged",
    "DUPLICATE_DISPUTED": "Complaint raised for the extra debit",
    "REVERSED": "Money returned on {rdate}",
    "SUCCEEDED": "Payment completed",
    "ESCALATED": "With a human expert",
    "ESCALATED_USER": "With a human expert",
    "REVIEWED": "Reviewed by a specialist",
    "RESOLVED_BY_RETRY": "Paid again successfully",
}


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


def _fill(tpl: str, facts: Facts, lang: str) -> str:
    return tpl.format(**facts.vars(lang))


def status_text(sit: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(STATUS[lang][sit], facts, lang)


def why_text(sit: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(WHY[lang][_WHY_KEYS.get(sit, sit)], facts, lang)


def what_if_text(sit: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    if sit == "DEBIT_WAIT":
        return _fill(WHAT_IF[lang], facts, lang)
    return status_text(sit, facts, lang)


def dispute_request_text(sit: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(DISPUTE_REQ[lang][_DISPUTE_KEYS.get(sit, "ESCALATED")], facts, lang)


def retry_text(key: str, facts: Facts, lang: str) -> str:
    lang = _lang(lang)
    return _fill(RETRY[lang][key], facts, lang)


def briefing_text(sit: str, facts: Facts, lang: str) -> str | None:
    lang = _lang(lang)
    key = _BRIEFING_KEYS.get(sit)
    return _fill(BRIEFING[lang][key], facts, lang) if key else None


def status_line(sit: str, facts: Facts) -> str:
    return _fill(STATUS_LINE.get(sit, ""), facts, "en")


def chips(sit: str, facts: Facts, lang: str) -> list[dict]:
    lang = _lang(lang)
    labels = CHIP_LABELS[lang]
    ids = {
        "RETRY_OFFER": ["retry", "why", "talk_to_human"],
        "DEBIT_WAIT": ["what_if", "why", "talk_to_human"],
        "ESCALATED": [], "ESCALATED_USER": [], "REVIEWED": ["talk_to_human"], "RESOLVED_BY_RETRY": [],
    }.get(sit, ["why", "talk_to_human"])
    return [{"id": i, "label": _fill(labels[i], facts, lang)} for i in ids]


# ------------------------------------------------------------------ number check (spec 10.2)
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {m.group().replace(",", "").rstrip(".") for m in _NUM.finditer(text)}


def number_check(text: str, facts_list: list[Facts], lang: str) -> list[str]:
    """Return numbers in `text` that don't come from the facts. Empty list = OK.
    Templates always pass; this guards the optional LLM rephrase (build step 7)."""
    allowed: set[str] = set()
    for f in facts_list:
        v = f.vars(_lang(lang))
        for key in ("amount", "date", "rdate", "ref", "comp", "days"):
            allowed |= _numbers(v[key])
    return sorted(_numbers(text) - allowed)
