"""The investigation shown in the chat right after a payment fails (team decision 3).

Three agents, each a view onto work the system really did for this payment:

  bank      NPCI status, bank ledger, merchant credit   (the evidence the decision used)
  rules     diagnosis F1-F10, the decision rule, retry  (DIAGNOSED / LLM_CLASSIFIED / DECIDED events, SLA
            safety, deadline, and the live re-check      deadline, the re-fetch done while opening)
  followup  what happens next without the user         (the queued job, deadline, dispute)

Nothing here is invented: every line is a template filled from those records, in the UI language.
The conclusion is the normal status answer, so follow-up questions continue exactly as before.
"""
import json
import math

from sqlalchemy.orm import Session

from app import clock
from app.config import Settings
from app.conversation import templates
from app.conversation.facts import case_facts, case_situation
from app.conversation.format import day_month, inr
from app.conversation.names import local_name
from app.engine import audit
from app.models import Case, Job, Transaction

AGENTS = ("bank", "rules", "followup")

NAMES = {
    "en": {"bank": "Bank agent", "rules": "Rules agent", "followup": "Follow-up agent"},
    "hi": {"bank": "बैंक एजेंट", "rules": "नियम एजेंट", "followup": "फ़ॉलो-अप एजेंट"},
    "mr": {"bank": "बँक एजंट", "rules": "नियम एजंट", "followup": "पाठपुरावा एजंट"},
}

T = {
    "en": {
        "intro_FAILED": "Your ₹{amount} payment to {payee} failed. I'm running a detailed investigation.",
        "intro_PENDING": "Your ₹{amount} payment to {payee} is stuck. I'm running a detailed investigation.",
        "done": "Investigation complete. ",
        "b_check": "Checking with NPCI, your bank and {payee}…",
        "s_live_same": "Re-checked everything live just now: nothing changed, so it's safe to tell you.",
        "s_live_changed": "Re-checked live just now: {sources} changed, so I decided again on the fresh data.", "n_status": "NPCI says: {status}{final}.", "n_down": "NPCI did not respond.", "final": " (final)", "b_none": "No money was taken from your account.",
        "b_debited": "₹{amount} was taken from your account.", "b_twice": "₹{amount} was taken twice.",
        "b_reversed": "The money already came back to your account.", "b_down": "Your bank did not respond.", "m_yes": "{payee} received the money.",
        "m_no": "{payee} did not receive it.", "m_down": "{payee}'s bank did not respond.",
        "d_conflict": "The sources disagree: {codes}.", "d_suspicious": "The claim doesn't match the records: {codes}.",
        "d_llm": "The rules couldn't place it, so the AI classifier helped (confidence {conf}).",
        "d_result": "Diagnosis: {label} ({code}).",
        "r_rule": "Rule {rule}: {action}.", "r_gate_ok": "Safe-retry check: every condition passed.",
        "r_no_retry": "Paying again is not safe right now.",
        "r_deadline": "The bank must return it by {date} (RBI T+{days}).",
        "f_deadline": "I'm watching the deadline: {date}.",
        "f_auto": "If the money isn't back by then, I'll raise a complaint myself and claim ₹{per_day} a day as compensation.",
        "f_disputed": "Complaint {ref} is raised. I'll follow up every day until it's settled.",
        "f_recheck": "I'll check again in {mins} minutes and tell you here.",
        "f_nothing_taken": "Nothing to chase: no money was taken.", "f_done": "Nothing left to chase.",
        "f_human": "A human expert has the full case file and will reply in this chat.",
    },
    "hi": {
        "intro_FAILED": "{payee} को आपका {amount} रुपये का पेमेंट असफल रहा। मैं इसकी पूरी जाँच कर रहा हूँ।",
        "intro_PENDING": "{payee} को आपका {amount} रुपये का पेमेंट अटका हुआ है। मैं इसकी पूरी जाँच कर रहा हूँ।",
        "done": "जाँच पूरी हुई। ",
        "b_check": "NPCI, आपके बैंक और {payee} से जानकारी ले रहा हूँ…",
        "s_live_same": "अभी-अभी सब कुछ दोबारा जाँचा: कुछ नहीं बदला, इसलिए आपको बताना सुरक्षित है।",
        "s_live_changed": "अभी-अभी दोबारा जाँचा: {sources} में बदलाव था, इसलिए नई जानकारी पर फ़ैसला दोबारा लिया।", "n_status": "NPCI के अनुसार: {status}{final}।", "n_down": "NPCI ने जवाब नहीं दिया।", "final": " (अंतिम)", "b_none": "आपके खाते से कोई पैसा नहीं कटा।",
        "b_debited": "आपके खाते से {amount} रुपये कटे।", "b_twice": "{amount} रुपये दो बार कटे।",
        "b_reversed": "पैसा पहले ही आपके खाते में वापस आ चुका है।", "b_down": "आपके बैंक ने जवाब नहीं दिया।", "m_yes": "{payee} को पैसा मिल गया।",
        "m_no": "{payee} को पैसा नहीं मिला।", "m_down": "{payee} के बैंक ने जवाब नहीं दिया।",
        "d_conflict": "स्रोतों की जानकारी आपस में मेल नहीं खाती: {codes}।",
        "d_suspicious": "दावा रिकॉर्ड से मेल नहीं खाता: {codes}।",
        "d_llm": "नियम इसे तय नहीं कर पाए, इसलिए AI ने मदद की (भरोसा {conf})।",
        "d_result": "निदान: {label} ({code})।",
        "r_rule": "नियम {rule}: {action}।", "r_gate_ok": "सुरक्षित-दोबारा-भुगतान जाँच: हर शर्त पूरी हुई।",
        "r_no_retry": "अभी दोबारा भेजना सुरक्षित नहीं है।",
        "r_deadline": "बैंक को {date} तक पैसा लौटाना है (RBI T+{days})।",
        "f_deadline": "मैं समय-सीमा पर नज़र रख रहा हूँ: {date}।",
        "f_auto": "अगर तब तक पैसा वापस नहीं आया, तो मैं खुद शिकायत दर्ज करूँगा और रोज़ {per_day} रुपये मुआवज़ा माँगूँगा।",
        "f_disputed": "शिकायत {ref} दर्ज है। मामला सुलझने तक मैं रोज़ फ़ॉलो-अप करूँगा।",
        "f_recheck": "मैं {mins} मिनट में फिर जाँच करूँगा और यहीं बताऊँगा।",
        "f_nothing_taken": "पीछा करने को कुछ नहीं: कोई पैसा नहीं कटा।", "f_done": "अब पीछा करने को कुछ बाकी नहीं।",
        "f_human": "एक विशेषज्ञ के पास पूरी केस फ़ाइल है, वे इसी चैट में जवाब देंगे।",
    },
    "mr": {
        "intro_FAILED": "{payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट अयशस्वी झाले. मी याची सविस्तर तपासणी करत आहे.",
        "intro_PENDING": "{payee} ला केलेले तुमचे {amount} रुपयांचे पेमेंट अडकले आहे. मी याची सविस्तर तपासणी करत आहे.",
        "done": "तपासणी पूर्ण झाली. ",
        "b_check": "NPCI, तुमची बँक आणि {payee} कडून माहिती घेत आहे…",
        "s_live_same": "आत्ताच सर्व पुन्हा तपासले: काहीही बदलले नाही, म्हणून तुम्हाला सांगणे सुरक्षित आहे.",
        "s_live_changed": "आत्ताच पुन्हा तपासले: {sources} मध्ये बदल होता, म्हणून नव्या माहितीवर निर्णय पुन्हा घेतला.", "n_status": "NPCI नुसार: {status}{final}.", "n_down": "NPCI ने प्रतिसाद दिला नाही.", "final": " (अंतिम)", "b_none": "तुमच्या खात्यातून पैसे कापले गेले नाहीत.",
        "b_debited": "तुमच्या खात्यातून {amount} रुपये कापले गेले.", "b_twice": "{amount} रुपये दोनदा कापले गेले.",
        "b_reversed": "पैसे आधीच तुमच्या खात्यात परत आले आहेत.", "b_down": "तुमच्या बँकेने प्रतिसाद दिला नाही.", "m_yes": "{payee} ला पैसे मिळाले.",
        "m_no": "{payee} ला पैसे मिळाले नाहीत.", "m_down": "{payee} च्या बँकेने प्रतिसाद दिला नाही.",
        "d_conflict": "स्रोतांची माहिती जुळत नाही: {codes}.", "d_suspicious": "दावा नोंदींशी जुळत नाही: {codes}.",
        "d_llm": "नियमांना ठरवता आले नाही, म्हणून AI ने मदत केली (खात्री {conf}).",
        "d_result": "निदान: {label} ({code}).",
        "r_rule": "नियम {rule}: {action}.", "r_gate_ok": "सुरक्षित पुनर्भरणा तपासणी: प्रत्येक अट पूर्ण झाली.",
        "r_no_retry": "आत्ता पुन्हा पाठवणे सुरक्षित नाही.",
        "r_deadline": "बँकेने {date} पर्यंत पैसे परत करायला हवेत (RBI T+{days}).",
        "f_deadline": "मी मुदतीवर लक्ष ठेवत आहे: {date}.",
        "f_auto": "तोपर्यंत पैसे परत आले नाहीत, तर मी स्वतः तक्रार नोंदवेन आणि दररोज {per_day} रुपये भरपाई मागेन.",
        "f_disputed": "तक्रार {ref} नोंदवली आहे. प्रकरण मिटेपर्यंत मी दररोज पाठपुरावा करेन.",
        "f_recheck": "मी {mins} मिनिटांनी पुन्हा तपासून इथेच सांगेन.",
        "f_nothing_taken": "पाठपुरावा करण्यासारखे काही नाही: पैसे कापले गेले नाहीत.",
        "f_done": "आता पाठपुरावा करण्यासारखे काही उरले नाही.",
        "f_human": "एका तज्ञाकडे प्रकरणाची संपूर्ण फाइल आहे, ते याच चॅटमध्ये उत्तर देतील.",
    },
}

NPCI_STATUS = {
    "en": {"SUCCESS": "successful", "FAILED": "failed", "PENDING": "still pending", "DEEMED": "deemed successful"},
    "hi": {"SUCCESS": "सफल", "FAILED": "असफल", "PENDING": "अभी लंबित", "DEEMED": "सफल माना गया"},
    "mr": {"SUCCESS": "यशस्वी", "FAILED": "अयशस्वी", "PENDING": "अजून प्रलंबित", "DEEMED": "यशस्वी मानले"},
}

CLASS_LABEL = {
    "en": {"F1": "declined before any money was taken", "F2": "timed out before any money was taken",
           "F3": "still being processed", "F4": "money taken but not delivered", "F5": "the payment actually went through",
           "F6": "the bank was down", "F7": "money taken twice", "F8": "money already returned",
           "F9": "the records don't match", "F10": "needs a closer look", "AMBIGUOUS": "couldn't be placed"},
    "hi": {"F1": "पैसा कटने से पहले ही अस्वीकार", "F2": "पैसा कटने से पहले ही समय समाप्त", "F3": "अभी प्रोसेस हो रहा है",
           "F4": "पैसा कटा पर पहुंचा नहीं", "F5": "पेमेंट असल में हो गया", "F6": "बैंक बंद था", "F7": "पैसा दो बार कटा",
           "F8": "पैसा पहले ही वापस आ गया", "F9": "रिकॉर्ड मेल नहीं खाते", "F10": "ध्यान से देखने की ज़रूरत",
           "AMBIGUOUS": "तय नहीं हो पाया"},
    "mr": {"F1": "पैसे कापण्याआधीच नाकारले", "F2": "पैसे कापण्याआधीच वेळ संपली", "F3": "अजून प्रक्रिया सुरू आहे",
           "F4": "पैसे कापले पण पोहोचले नाहीत", "F5": "पेमेंट प्रत्यक्षात झाले", "F6": "बँक बंद होती",
           "F7": "पैसे दोनदा कापले", "F8": "पैसे आधीच परत आले", "F9": "नोंदी जुळत नाहीत", "F10": "बारकाईने पाहण्याची गरज",
           "AMBIGUOUS": "ठरवता आले नाही"},
}

ACTION_LABEL = {
    "en": {"WAIT": "wait", "OFFER_RETRY": "safe to pay again", "RAISE_DISPUTE": "raise a complaint",
           "CLOSE": "close the case", "ESCALATE": "send to a human expert"},
    "hi": {"WAIT": "इंतज़ार करना", "OFFER_RETRY": "दोबारा भेजना सुरक्षित", "RAISE_DISPUTE": "शिकायत दर्ज करना",
           "CLOSE": "केस बंद करना", "ESCALATE": "विशेषज्ञ को भेजना"},
    "mr": {"WAIT": "थांबणे", "OFFER_RETRY": "पुन्हा पाठवणे सुरक्षित", "RAISE_DISPUTE": "तक्रार नोंदवणे",
           "CLOSE": "प्रकरण बंद करणे", "ESCALATE": "तज्ञाकडे पाठवणे"},
}

LEDGER_SHORT = {
    "en": {"NO_DEBIT": "no debit", "DEBITED": "debited", "REVERSED": "returned", None: "no reply"},
    "hi": {"NO_DEBIT": "कोई कटौती नहीं", "DEBITED": "पैसा कटा", "REVERSED": "पैसा लौटा", None: "जवाब नहीं"},
    "mr": {"NO_DEBIT": "कपात नाही", "DEBITED": "पैसे कापले", "REVERSED": "पैसे परत", None: "प्रतिसाद नाही"},
}

SOURCE_LABEL = {
    "en": {"NPCI": "NPCI", "BANK_LEDGER": "bank", "MERCHANT": "merchant"},
    "hi": {"NPCI": "NPCI", "BANK_LEDGER": "बैंक", "MERCHANT": "व्यापारी"},
    "mr": {"NPCI": "NPCI", "BANK_LEDGER": "बँक", "MERCHANT": "व्यापारी"},
}


def _latest(db: Session, case_id: str, event_type: str) -> dict | None:
    for e in reversed(audit.events(db, case_id)):
        if e.event_type == event_type:
            return json.loads(e.payload_json or "{}")
    return None


def _agent(key: str, lang: str, lines: list[str], tone: str, verdict: str) -> dict:
    return {"id": key, "name": NAMES[lang][key], "lines": lines, "tone": tone, "verdict": verdict}


def intro_text(txn: Transaction, lang: str) -> str:
    key = "intro_PENDING" if txn.status == "PENDING" else "intro_FAILED"
    return T[lang][key].format(amount=inr(txn.amount_paise), payee=local_name(txn.payee_name, lang))


def conclusion_text(db: Session, case: Case, lang: str) -> str:
    return T[lang]["done"] + templates.status_text(case_situation(case), case_facts(db, case), lang)


def build(db: Session, settings: Settings, case: Case, txn: Transaction, lang: str,
          changed_sources: list[str]) -> list[dict]:
    t = T[lang]
    ev = json.loads(case.evidence_json or "{}")
    n, led, m = ev.get("npci", {}), ev.get("ledger", {}), ev.get("merchant", {})
    amount, payee = inr(txn.amount_paise), local_name(txn.payee_name, lang)
    agents = []

    # Bank agent: where the money is (NPCI status, the bank ledger, the merchant's credit)
    lines = [t["b_check"].format(payee=payee)]
    if n.get("available", True) and n.get("status"):
        lines.append(t["n_status"].format(status=NPCI_STATUS[lang].get(n["status"], n["status"]),
                                          final=t["final"] if n.get("final") else ""))
    else:
        lines.append(t["n_down"])
    state = led.get("state") if led.get("available", True) else None
    if state == "DEBITED":
        lines.append((t["b_twice"] if (led.get("debit_count") or 1) >= 2 else t["b_debited"]).format(amount=amount))
    elif state == "REVERSED":
        lines.append(t["b_reversed"])
    elif state == "NO_DEBIT":
        lines.append(t["b_none"])
    else:
        lines.append(t["b_down"])
    if not m.get("available", True):
        lines.append(t["m_down"].format(payee=payee))
    else:
        lines.append((t["m_yes"] if m.get("credited") else t["m_no"]).format(payee=payee))
    bank_tone = "bad" if state == "DEBITED" and not m.get("credited") else "ok" if state in ("NO_DEBIT", "REVERSED") else "warn"
    agents.append(_agent("bank", lang, lines, bank_tone, LEDGER_SHORT[lang].get(state, LEDGER_SHORT[lang][None])))

    # Rules agent: diagnosis, the decision rule, retry safety, deadline, and the live re-check
    diag = _latest(db, case.id, "DIAGNOSED") or {}
    llm = _latest(db, case.id, "LLM_CLASSIFIED")
    lines = []
    conflicts = json.loads(case.conflicts_json or "[]")
    sus = [c["code"] for c in conflicts if c["code"].startswith(("CLAIM_", "REPEAT_"))]
    conf = [c["code"] for c in conflicts if c["code"] not in sus]
    if conf:
        lines.append(t["d_conflict"].format(codes=", ".join(conf)))
    if sus:
        lines.append(t["d_suspicious"].format(codes=", ".join(sus)))
    if llm and llm.get("result"):
        lines.append(t["d_llm"].format(conf=f"{llm['result'].get('confidence', 0):.2f}"))
    code = str(case.class_ or diag.get("case_class") or "AMBIGUOUS").split("_")[0]
    lines.append(t["d_result"].format(label=CLASS_LABEL[lang].get(code, code), code=code))
    action = case.decision or "ESCALATE"
    lines.append(t["r_rule"].format(rule=case.rule_id or "8", action=ACTION_LABEL[lang].get(action, action)))
    if action == "OFFER_RETRY":
        lines.append(t["r_gate_ok"])
    elif state != "NO_DEBIT" or n.get("status") != "FAILED" or not n.get("final"):
        lines.append(t["r_no_retry"])
    sit = case_situation(case)
    if sit == "DEBIT_WAIT" and case.deadline_ts:
        lines.append(t["r_deadline"].format(date=day_month(case.deadline_ts, lang),
                                            days=settings.SLA_BENEFICIARY_CREDIT_FAILURE_DAYS))
    if changed_sources:
        lines.append(t["s_live_changed"].format(
            sources=", ".join(SOURCE_LABEL[lang].get(src, src) for src in changed_sources)))
    else:
        lines.append(t["s_live_same"])
    agents.append(_agent("rules", lang, lines, "bad" if action == "ESCALATE" else "warn" if changed_sources else "ok",
                         ACTION_LABEL[lang].get(action, action)))

    # Follow-up agent
    facts = case_facts(db, case)
    if sit == "DEBIT_WAIT" and case.deadline_ts:
        lines = [t["f_deadline"].format(date=day_month(case.deadline_ts, lang)),
                 t["f_auto"].format(per_day=settings.COMPENSATION_PER_DAY)]
    elif sit in ("DISPUTED", "DUPLICATE_DISPUTED"):
        lines = [t["f_disputed"].format(ref=facts.dispute_ref or "")]
    elif sit in ("PENDING", "BANK_DOWN", "PRE_DEBIT_WAIT"):
        job = (db.query(Job).filter(Job.case_id == case.id, Job.status == "QUEUED").order_by(Job.run_at).first())
        mins = (max(1, math.ceil((job.run_at - clock.now(db)).total_seconds() / 60)) if job
                else settings.RECHECK_INTERVAL_MINUTES)
        lines = [t["f_recheck"].format(mins=mins)]
    elif sit == "RETRY_OFFER":
        lines = [t["f_nothing_taken"]]
    elif sit in ("ESCALATED", "ESCALATED_USER", "REVIEWED"):
        lines = [t["f_human"]]
    else:
        lines = [t["f_done"]]
    agents.append(_agent("followup", lang, lines, "ok", ""))
    return agents
