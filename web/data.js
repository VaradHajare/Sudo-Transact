/*
 * data.js: brand, formatters, and the API client.
 *
 * The backend owns the data. This file keeps only formatting helpers and the repositories that
 * call /v1 on the same origin. Every repository method is async (returns a Promise).
 * Amounts are integer paise everywhere; format them only for display.
 */
(function () {
  "use strict";

  // The ONLY place the app name appears.
  const BRAND = Object.freeze({
    appName: "Paytm",
    assistantName: "AI Resolve",
    prototypeLabel: "Prototype · mock data, no real money",
  });

  // ------------------------------------------------------------------ UI language (toggle)
  // The app's language. The agent answers in it too (sent to the backend as X-UI-Lang).
  // Kept in localStorage: a per-viewer preference, safe to lose.
  const UI_LANGS = [["en", "EN"], ["hi", "हिं"], ["mr", "मरा"]];
  let uiLang = (() => { try { return localStorage.getItem("ui_lang") || "en"; } catch { return "en"; } })();
  if (!UI_LANGS.some(([l]) => l === uiLang)) uiLang = "en";

  // All UI text. {name} placeholders are filled by t(key, vars). Hindi and Marathi need a native
  // speaker's review before the demo, like the backend templates.
  const I18N = {
    en: {
      prototype: "Prototype · mock data, no real money",
      scanPay: "Scan & Pay", toMobile: "To Mobile", toBank: "To Bank", balance: "Balance",
      recent: "Recent payments", seeAll: "See all",
      demoTools: "Demo controls (mock world): move the simulated clock forward so deadlines pass.",
      skipDay: "Skip time +1 day", loadingPayments: "Loading payments…", loadingPayment: "Loading payment…",
      loading: "Loading…", tryAgain: "Try again", notFound: "Payment not found.", noPayments: "No payments yet.",
      history: "Payment history", askAbout: "Ask about {name}", txnDetails: "Transaction details",
      SUCCESS: "Successful", FAILED: "Failed", PENDING: "Pending",
      hSUCCESS: "Payment successful", hFAILED: "Payment failed", hPENDING: "Payment pending",
      moneyReceived: "Money received", to: "to", from: "from", receivedFrom: "Received from {name}",
      toUpi: "To UPI ID", fromUpi: "From UPI ID", dateTime: "Date & time", upiRef: "UPI Ref No.",
      paidVia: "Paid via", note: "Note", reason: "Reason",
      micFAILED: "Payment failed? Ask me", micPENDING: "Payment pending? Ask me", talkTo: "talk to {name}",
      newUpdate: "New update", next: "Next", expectedBy: "expected by {date}", update: "Update",
      today: "Today", yesterday: "Yesterday", back: "Back", language: "Language",
      aboutPayment: "About this payment only", textMode: "text mode",
      askTitle: "Ask about this payment",
      askVoice: "I already know which payment you mean. Tap the mic and speak, or type.",
      askText: "I already know which payment you mean. Type your question.",
      speak: "Speak", voiceOff: "Voice is off on the server. Please type.", typeQuestion: "Type your question…",
      send: "Send", yourMessage: "Your message", mute: "Mute replies", unmute: "Unmute replies",
      listening: "Listening…", thinking: "Thinking…", speaking: "Speaking… tap the orb to interrupt",
      orbInterrupt: "Interrupt and speak", orbSend: "Done speaking, send now", working: "Working",
      typeInstead: "Type instead", endVoice: "End voice conversation",
      didntCatch: "I didn't catch that. Please say it again, or type.",
      voiceUnavailable: "Voice is unavailable right now. Please type your question.",
      couldntSend: "Couldn't send: {msg}", voicePaused: "Voice paused. Tap the mic when you want to talk again.",
      couldntHear: "I couldn't hear you clearly. Tap the mic to try again, or type.",
      sayAgain: "Sorry, I didn't catch that. Please say it again.",
      cantRecord: "This browser can't record audio. Please type.",
      pay: "Pay", retrySubtitle: "Retry of a failed payment",
      noRetry: "No confirmed retry for this payment. Go back to the chat and ask again.",
      enterPin: "Enter UPI PIN (mock, any 4–6 digits)", pinDigits: "PIN must be 4 to 6 digits.", payAmount: "Pay {amount}",
      paid: "Paid", backToChat: "Back to chat", home: "Home",
      scanTitle: "Scan any QR", scanSub: "Demo: a merchant QR is scanned for you",
      pointCamera: "Point your camera at a QR code", couldntScan: "Couldn't scan: {msg}",
      scannedQr: "Scanned QR", fromQr: "from QR", amount: "Amount", addNote: "Add a note (optional)",
      proceed: "Proceed to pay", amountRange: "Enter an amount between ₹1 and ₹1,00,000.",
      payingTo: "Paying {amount} to {payee}", paying: "Paying {amount} to {payee}…",
      investigating: "{assistant} is investigating what happened…",
      invTitle: "Detailed investigation", invAgents: "{n} agents", agentThinking: "thinking",
      micBlocked: "Microphone permission is blocked. Allow it in the browser, or type instead.",
      noMic: "No microphone available. Please type instead.", listenHint: "Listening… speak in any language",
      gotIt: "Got it…", stopSend: "Stop listening and send", micStarting: "Starting the microphone…", cancel: "Cancel",
      callTitle: "Support specialist", callNow: "Call now", calling: "Calling…",
    },
    hi: {
      prototype: "प्रोटोटाइप · नकली डेटा, असली पैसा नहीं",
      scanPay: "स्कैन करके भेजें", toMobile: "मोबाइल पर", toBank: "बैंक में", balance: "बैलेंस",
      recent: "हाल के पेमेंट", seeAll: "सभी देखें",
      demoTools: "डेमो कंट्रोल (नकली दुनिया): समय आगे बढ़ाएँ ताकि समय-सीमा निकल जाए।",
      skipDay: "समय +1 दिन आगे", loadingPayments: "पेमेंट लोड हो रहे हैं…", loadingPayment: "पेमेंट लोड हो रहा है…",
      loading: "लोड हो रहा है…", tryAgain: "फिर कोशिश करें", notFound: "पेमेंट नहीं मिला।", noPayments: "अभी कोई पेमेंट नहीं।",
      history: "पेमेंट इतिहास", askAbout: "{name} के बारे में पूछें", txnDetails: "लेन-देन का विवरण",
      SUCCESS: "सफल", FAILED: "असफल", PENDING: "लंबित",
      hSUCCESS: "पेमेंट सफल", hFAILED: "पेमेंट असफल", hPENDING: "पेमेंट लंबित",
      moneyReceived: "पैसा मिला", to: "को", from: "से", receivedFrom: "{name} से मिला",
      toUpi: "पाने वाले की UPI ID", fromUpi: "भेजने वाले की UPI ID", dateTime: "तारीख और समय", upiRef: "UPI रेफ़ नंबर",
      paidVia: "भुगतान का माध्यम", note: "नोट", reason: "कारण",
      micFAILED: "पेमेंट असफल? मुझसे पूछें", micPENDING: "पेमेंट लंबित? मुझसे पूछें", talkTo: "{name} से बात करें",
      newUpdate: "नई जानकारी", next: "आगे", expectedBy: "{date} तक अपेक्षित", update: "नई जानकारी",
      today: "आज", yesterday: "कल", back: "वापस", language: "भाषा",
      aboutPayment: "सिर्फ़ इसी पेमेंट के बारे में", textMode: "टेक्स्ट मोड",
      askTitle: "इस पेमेंट के बारे में पूछें",
      askVoice: "मुझे पता है आप किस पेमेंट की बात कर रहे हैं। माइक दबाकर बोलें, या लिखें।",
      askText: "मुझे पता है आप किस पेमेंट की बात कर रहे हैं। अपना सवाल लिखें।",
      speak: "बोलें", voiceOff: "सर्वर पर आवाज़ बंद है। कृपया लिखें।", typeQuestion: "अपना सवाल लिखें…",
      send: "भेजें", yourMessage: "आपका संदेश", mute: "जवाब की आवाज़ बंद करें", unmute: "जवाब की आवाज़ चालू करें",
      listening: "सुन रहा हूँ…", thinking: "सोच रहा हूँ…", speaking: "बोल रहा हूँ… बीच में बोलने के लिए गोला दबाएँ",
      orbInterrupt: "रोकें और बोलें", orbSend: "बोल लिया, अभी भेजें", working: "काम चल रहा है",
      typeInstead: "लिखकर पूछें", endVoice: "आवाज़ वाली बातचीत बंद करें",
      didntCatch: "मैं समझ नहीं पाया। कृपया फिर से बोलें, या लिखें।",
      voiceUnavailable: "अभी आवाज़ उपलब्ध नहीं है। कृपया अपना सवाल लिखें।",
      couldntSend: "भेजा नहीं जा सका: {msg}", voicePaused: "आवाज़ रुकी है। बात करनी हो तो माइक दबाएँ।",
      couldntHear: "मैं ठीक से सुन नहीं पाया। माइक दबाकर फिर कोशिश करें, या लिखें।",
      sayAgain: "माफ़ कीजिए, समझ नहीं आया। कृपया फिर से बोलें।",
      cantRecord: "यह ब्राउज़र आवाज़ रिकॉर्ड नहीं कर सकता। कृपया लिखें।",
      pay: "भेजें", retrySubtitle: "असफल पेमेंट दोबारा",
      noRetry: "इस पेमेंट के लिए दोबारा भेजने की पुष्टि नहीं हुई है। चैट में वापस जाकर फिर पूछें।",
      enterPin: "UPI PIN डालें (नकली, कोई भी 4–6 अंक)", pinDigits: "PIN 4 से 6 अंकों का होना चाहिए।", payAmount: "{amount} भेजें",
      paid: "भेज दिया", backToChat: "चैट पर वापस", home: "होम",
      scanTitle: "कोई भी QR स्कैन करें", scanSub: "डेमो: एक दुकान का QR अपने आप स्कैन होगा",
      pointCamera: "कैमरा QR कोड की ओर करें", couldntScan: "स्कैन नहीं हो सका: {msg}",
      scannedQr: "स्कैन किया गया QR", fromQr: "QR से", amount: "रकम", addNote: "नोट जोड़ें (वैकल्पिक)",
      proceed: "आगे बढ़ें", amountRange: "₹1 से ₹1,00,000 के बीच रकम डालें।",
      payingTo: "{payee} को {amount} भेज रहे हैं", paying: "{payee} को {amount} भेज रहे हैं…",
      investigating: "{assistant} जाँच कर रहा है कि क्या हुआ…",
      invTitle: "पूरी जाँच", invAgents: "{n} एजेंट", agentThinking: "सोच रहा है",
      micBlocked: "माइक की अनुमति बंद है। ब्राउज़र में अनुमति दें, या लिखें।",
      noMic: "कोई माइक नहीं मिला। कृपया लिखें।", listenHint: "सुन रहा हूँ… किसी भी भाषा में बोलें",
      gotIt: "समझ गया…", stopSend: "सुनना बंद करें और भेजें", micStarting: "माइक चालू हो रहा है…", cancel: "रद्द करें",
      callTitle: "सहायता विशेषज्ञ", callNow: "अभी कॉल करें", calling: "कॉल लग रही है…",
    },
    mr: {
      prototype: "प्रोटोटाइप · बनावट डेटा, खरे पैसे नाहीत",
      scanPay: "स्कॅन करून पाठवा", toMobile: "मोबाईलवर", toBank: "बँकेत", balance: "शिल्लक",
      recent: "अलीकडील पेमेंट", seeAll: "सर्व पाहा",
      demoTools: "डेमो नियंत्रणे (बनावट जग): मुदत संपावी म्हणून वेळ पुढे न्या.",
      skipDay: "वेळ +1 दिवस पुढे", loadingPayments: "पेमेंट लोड होत आहेत…", loadingPayment: "पेमेंट लोड होत आहे…",
      loading: "लोड होत आहे…", tryAgain: "पुन्हा प्रयत्न करा", notFound: "पेमेंट सापडले नाही.", noPayments: "अजून कोणतेही पेमेंट नाही.",
      history: "पेमेंट इतिहास", askAbout: "{name} बद्दल विचारा", txnDetails: "व्यवहाराचा तपशील",
      SUCCESS: "यशस्वी", FAILED: "अयशस्वी", PENDING: "प्रलंबित",
      hSUCCESS: "पेमेंट यशस्वी", hFAILED: "पेमेंट अयशस्वी", hPENDING: "पेमेंट प्रलंबित",
      moneyReceived: "पैसे मिळाले", to: "ला", from: "कडून", receivedFrom: "{name} कडून मिळाले",
      toUpi: "घेणाऱ्याचा UPI ID", fromUpi: "पाठवणाऱ्याचा UPI ID", dateTime: "तारीख आणि वेळ", upiRef: "UPI रेफ क्रमांक",
      paidVia: "पेमेंटचे माध्यम", note: "टीप", reason: "कारण",
      micFAILED: "पेमेंट अयशस्वी? मला विचारा", micPENDING: "पेमेंट प्रलंबित? मला विचारा", talkTo: "{name} शी बोला",
      newUpdate: "नवीन माहिती", next: "पुढे", expectedBy: "{date} पर्यंत अपेक्षित", update: "नवीन माहिती",
      today: "आज", yesterday: "काल", back: "मागे", language: "भाषा",
      aboutPayment: "फक्त याच पेमेंटबद्दल", textMode: "मजकूर मोड",
      askTitle: "या पेमेंटबद्दल विचारा",
      askVoice: "तुम्ही कोणत्या पेमेंटबद्दल बोलत आहात ते मला माहीत आहे. माइक दाबून बोला, किंवा लिहा.",
      askText: "तुम्ही कोणत्या पेमेंटबद्दल बोलत आहात ते मला माहीत आहे. तुमचा प्रश्न लिहा.",
      speak: "बोला", voiceOff: "सर्व्हरवर आवाज बंद आहे. कृपया लिहा.", typeQuestion: "तुमचा प्रश्न लिहा…",
      send: "पाठवा", yourMessage: "तुमचा संदेश", mute: "उत्तरांचा आवाज बंद करा", unmute: "उत्तरांचा आवाज सुरू करा",
      listening: "ऐकत आहे…", thinking: "विचार करत आहे…", speaking: "बोलत आहे… मध्ये बोलण्यासाठी गोल दाबा",
      orbInterrupt: "थांबवा आणि बोला", orbSend: "बोलून झाले, आत्ता पाठवा", working: "काम सुरू आहे",
      typeInstead: "लिहून विचारा", endVoice: "आवाजातील संवाद बंद करा",
      didntCatch: "मला समजले नाही. कृपया पुन्हा बोला, किंवा लिहा.",
      voiceUnavailable: "आत्ता आवाज उपलब्ध नाही. कृपया तुमचा प्रश्न लिहा.",
      couldntSend: "पाठवता आले नाही: {msg}", voicePaused: "आवाज थांबला आहे. बोलायचे असेल तेव्हा माइक दाबा.",
      couldntHear: "मला नीट ऐकू आले नाही. माइक दाबून पुन्हा प्रयत्न करा, किंवा लिहा.",
      sayAgain: "माफ करा, समजले नाही. कृपया पुन्हा बोला.",
      cantRecord: "हा ब्राउझर आवाज रेकॉर्ड करू शकत नाही. कृपया लिहा.",
      pay: "पाठवा", retrySubtitle: "अयशस्वी पेमेंट पुन्हा",
      noRetry: "या पेमेंटसाठी पुन्हा पाठवण्याची पुष्टी झालेली नाही. चॅटमध्ये परत जाऊन पुन्हा विचारा.",
      enterPin: "UPI PIN टाका (बनावट, कोणतेही 4–6 अंक)", pinDigits: "PIN 4 ते 6 अंकांचा हवा.", payAmount: "{amount} पाठवा",
      paid: "पाठवले", backToChat: "चॅटवर परत", home: "होम",
      scanTitle: "कोणताही QR स्कॅन करा", scanSub: "डेमो: एका दुकानाचा QR आपोआप स्कॅन होईल",
      pointCamera: "कॅमेरा QR कोडकडे धरा", couldntScan: "स्कॅन झाले नाही: {msg}",
      scannedQr: "स्कॅन केलेला QR", fromQr: "QR वरून", amount: "रक्कम", addNote: "टीप जोडा (ऐच्छिक)",
      proceed: "पुढे जा", amountRange: "₹1 ते ₹1,00,000 दरम्यान रक्कम टाका.",
      payingTo: "{payee} ला {amount} पाठवत आहे", paying: "{payee} ला {amount} पाठवत आहे…",
      investigating: "{assistant} काय झाले ते तपासत आहे…",
      invTitle: "सविस्तर तपासणी", invAgents: "{n} एजंट", agentThinking: "विचार करत आहे",
      micBlocked: "माइकची परवानगी बंद आहे. ब्राउझरमध्ये परवानगी द्या, किंवा लिहा.",
      noMic: "माइक उपलब्ध नाही. कृपया लिहा.", listenHint: "ऐकत आहे… कोणत्याही भाषेत बोला",
      gotIt: "समजले…", stopSend: "ऐकणे थांबवा आणि पाठवा", micStarting: "माइक सुरू होत आहे…", cancel: "रद्द करा",
      callTitle: "सहाय्यता तज्ञ", callNow: "आत्ता कॉल करा", calling: "कॉल लागत आहे…",
    },
  };

  /** UI text in the current language, with {name} placeholders filled (falls back to English). */
  function t(key, vars) {
    const s = (I18N[uiLang] && I18N[uiLang][key]) || I18N.en[key] || key;
    return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : s;
  }
  function getUiLang() { return uiLang; }
  function setUiLang(lang) {
    if (!I18N[lang]) return;
    uiLang = lang;
    try { localStorage.setItem("ui_lang", lang); } catch { /* memory only */ }
    document.documentElement.lang = lang;
  }
  document.documentElement.lang = uiLang;

  // ------------------------------------------------------------------ formatters (in the UI language)
  const IST = "Asia/Kolkata";
  const fmtCache = {};
  function fmt(kind) {
    const key = uiLang + kind;
    if (!fmtCache[key]) {
      const opts = {
        time: { hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST },
        day: { day: "numeric", month: "short", timeZone: IST },
        full: { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST },
      }[kind];
      fmtCache[key] = new Intl.DateTimeFormat(`${uiLang}-IN`, { ...opts, numberingSystem: "latn" });
    }
    return fmtCache[key];
  }
  const dateKey = (d) => d.toLocaleDateString("en-CA", { timeZone: IST });

  /** 149900 -> "₹1,499"; 12345 -> "₹123.45" (digits stay Latin in every UI language) */
  function formatPaise(paise) {
    const rupees = Math.abs(paise) / 100;
    const opts = Number.isInteger(rupees) ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    return (paise < 0 ? "-" : "") + "₹" + rupees.toLocaleString("en-IN", opts);
  }

  /** ISO timestamp -> "Today, 11:19 am" / "आज, 11:19 am" / "29 Sep, 6:05 pm" */
  function formatWhen(iso) {
    const d = new Date(iso);
    const now = new Date();
    const yesterday = new Date(now.getTime() - 86400000);
    const day = dateKey(d) === dateKey(now) ? t("today") : dateKey(d) === dateKey(yesterday) ? t("yesterday") : fmt("day").format(d);
    return `${day}, ${fmt("time").format(d)}`;
  }

  function formatFull(iso) {
    return fmt("full").format(new Date(iso));
  }

  /** "2026-10-04" -> "4 Oct" (in the UI language) */
  function formatDay(isoDate) {
    if (!isoDate) return "";
    return fmt("day").format(new Date(isoDate + "T12:00:00+05:30"));
  }

  /** STATUS_LABEL.FAILED -> "Failed" / "असफल" / "अयशस्वी" (follows the UI language) */
  const STATUS_LABEL = new Proxy({}, { get: (_o, status) => t(String(status)) });

  // ------------------------------------------------------------------ HTTP
  const store = {
    get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch { /* storage unavailable: memory only */ } },
    del(k) { try { sessionStorage.removeItem(k); } catch { /* ignore */ } },
  };
  let token = store.get("st_token");

  function newKey() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "k-" + Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  class ApiError extends Error {
    constructor(status, detail) {
      super(typeof detail === "string" ? detail : JSON.stringify(detail));
      this.status = status;
      this.detail = detail;
    }
  }

  async function ensureSession(force) {
    if (token && !force) return token;
    const res = await fetch("/v1/session", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
    });
    if (!res.ok) throw new ApiError(res.status, "Could not start a session");
    token = (await res.json()).token;
    store.set("st_token", token);
    return token;
  }

  /** body: undefined | plain object (sent as JSON) | FormData (sent as multipart, e.g. audio). */
  async function api(method, path, body, { idempotent = false, retried = false, key } = {}) {
    await ensureSession();
    const isForm = typeof FormData !== "undefined" && body instanceof FormData;
    const headers = { Authorization: `Bearer ${token}`, "X-UI-Lang": uiLang };
    if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    const idemKey = idempotent ? key || newKey() : null;
    if (idemKey) headers["Idempotency-Key"] = idemKey;
    const payload = body === undefined ? undefined : isForm ? body : JSON.stringify(body);
    const res = await fetch(path, { method, headers, body: payload });
    if (res.status === 401 && !retried) {
      await ensureSession(true);
      return api(method, path, body, { idempotent, retried: true, key: idemKey });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, data.detail || res.statusText);
    return data;
  }

  // ------------------------------------------------------------------ repositories
  // Transaction shape (camelCase): { id, payeeName, payeeVpa, amountPaise, status, debited, timestamp,
  //   note, direction, category, railLabel, upiRef, failureReason, case: {id, state, situation, hasUpdate, statusLine} | null }
  const TransactionRepository = {
    /** @returns {Promise<Array>} newest first */
    async list() {
      return (await api("GET", "/v1/transactions")).transactions;
    },
    /** @returns {Promise<Object>} */
    async get(id) {
      return api("GET", `/v1/transactions/${encodeURIComponent(id)}`);
    },
    /** Mock pay screen. A retry must match the confirmed retry payload. origin: "scan" | "retry". */
    async pay({ payee_vpa, payee_name, amount_paise, note, pin, retry_of_case_id, origin }) {
      return api("POST", "/v1/payments", { payee_vpa, payee_name, amount_paise, note, pin, retry_of_case_id, origin }, { idempotent: true });
    },
    /** Mock QR scan (demo): the backend returns the decoded merchant { payee_name, payee_vpa }. */
    async scan() {
      return api("POST", "/v1/scan");
    },
  };

  const AgentRepository = {
    /** User tapped the mic on this payment: one session per payment. With investigate (the payment
     *  just failed in front of the user) the response carries `investigation`: {intro, agents, conclusion}. */
    async openCase(txnId, { investigate = false } = {}) {
      const body = { txn_id: txnId };
      if (investigate) body.investigate = true;
      return api("POST", "/v1/cases/open", body);
    },
    /** One turn: text, or a chip id. */
    async sendTurn(caseId, { text, chipId, lang } = {}) {
      const body = { case_id: caseId };
      if (text) body.text = text;
      if (chipId) body.chip_id = chipId;
      if (lang) body.lang = lang;
      return api("POST", "/v1/voice/turn", body, { idempotent: true });
    },
    /** One spoken turn: the recorded audio goes to the backend (Sarvam STT there; no key in the app). */
    async sendVoice(caseId, blob, { lang } = {}) {
      const form = new FormData();
      form.append("case_id", caseId);
      if (lang) form.append("lang", lang);
      const ext = (blob.type || "").includes("ogg") ? "ogg" : (blob.type || "").includes("mp4") ? "m4a" : "webm";
      form.append("audio", blob, `speech.${ext}`);
      return api("POST", "/v1/voice/turn", form, { idempotent: true });
    },
    /** "Pay ₹X again": live re-check + retry gate on the backend. */
    async confirmRetry(caseId) {
      return api("POST", `/v1/cases/${encodeURIComponent(caseId)}/retry/confirm`, undefined, { idempotent: true });
    },
    async messages(caseId) {
      return (await api("GET", `/v1/cases/${encodeURIComponent(caseId)}/messages`)).messages;
    },
  };

  // Pay-screen payloads handed from the chat to #/pay/:caseId (only ever set from an OPEN_PAY_SCREEN action).
  const PendingPayments = {
    set(caseId, payload) { store.set("pay_" + caseId, JSON.stringify(payload)); },
    get(caseId) { try { return JSON.parse(store.get("pay_" + caseId)); } catch { return null; } },
    clear(caseId) { store.del("pay_" + caseId); },
  };

  // What the server has switched on (voice, LLM). Cached for the page's lifetime.
  let healthPromise = null;
  const ConfigRepository = {
    async health() {
      if (!healthPromise) {
        healthPromise = fetch("/healthz").then((r) => r.json()).catch(() => ({ stt: false, tts: false }));
      }
      return healthPromise;
    },
  };

  // Recorded audio handed from the listening sheet (on any screen) to the chat for that payment.
  const PendingVoice = (() => {
    const byTxn = new Map();
    return {
      set(txnId, value) { byTxn.set(txnId, value); },
      take(txnId) { const v = byTxn.get(txnId); byTxn.delete(txnId); return v || null; },
    };
  })();

  // The QR just scanned, handed from #/scan to #/send (payee details come from the QR, never typed).
  const PendingScan = {
    set(qr) { store.set("scan_qr", JSON.stringify(qr)); },
    get() { try { return JSON.parse(store.get("scan_qr")); } catch { return null; } },
    clear() { store.del("scan_qr"); },
  };

  // A payment that just failed in front of the user: its chat opens with the agent's investigation.
  const PendingInvestigation = (() => {
    const txns = new Set();
    return {
      set(txnId) { txns.add(txnId); },
      take(txnId) { const had = txns.has(txnId); txns.delete(txnId); return had; },
    };
  })();

  // Small per-viewer conveniences (never business state).
  const Prefs = {
    get muted() { return store.get("pref_muted") === "1"; },
    set muted(v) { store.set("pref_muted", v ? "1" : "0"); },
    get lastLang() { return uiLang; }, // the speech-recognition hint follows the UI language
    set lastLang(_v) { /* replies come back in the UI language */ },
  };

  /*
   * Voice settings. The live transcript in the listening sheet uses the browser's speech
   * recognizer only as a preview while the user talks (in Chrome that audio is processed by
   * Google); the transcript that counts comes from Sarvam via the backend. Set
   * liveTranscript: false to show only the voice-level orb.
   */
  const VOICE = Object.freeze({
    liveTranscript: true,
    silenceMs: 2000, // end of speech after this much silence (room for slow speakers to pause)
    noSpeechMs: 20000, // nobody spoke for this long: a hands-free conversation pauses
    maxMisses: 3, // "didn't catch that" this many times in a row: the conversation pauses
    maxMs: 30000, // longest single turn
    handsFree: true, // after a spoken reply, listen again automatically (Siri-style)
    speechLevel: 0.04, // minimum RMS that counts as speech (raised automatically in noisy rooms)
    noiseFactor: 3, // speech must be this many times louder than the measured room noise
    wordMs: 45, // reply text reveal speed when there is no audio to follow (muted)
    agentThinkMs: 650, // investigation: how long each agent "thinks" before its first line
    agentLineMs: 420, // investigation: pause between an agent's lines
  });
  const LANG_TAG = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };

  // Ops console (console.html): escalation queue, reviewer decisions, agent activity, evaluation.
  const ReviewRepository = {
    /** Escalated cases with their case files. */
    async queue() {
      return (await api("GET", "/v1/review/queue")).cases;
    },
    /** Every case, most recently active first. */
    async cases() {
      return (await api("GET", "/v1/review/cases")).cases;
    },
    /** { case, case_file, reviews, events } */
    async detail(caseId) {
      return api("GET", `/v1/review/cases/${encodeURIComponent(caseId)}`);
    },
    /** decision: "APPROVE" | "REJECT" | "REQUEST_INFO". Notes stay internal. */
    async decide(caseId, decision, notes) {
      return api("POST", `/v1/review/${encodeURIComponent(caseId)}/decision`,
        { decision, notes: notes || null, reviewer: "console" }, { idempotent: true });
    },
    /** Latest simulator report, or null if none has been run. */
    async evaluation() {
      try {
        return await api("GET", "/v1/review/evaluation");
      } catch (e) {
        if (e.status === 404) return null;
        throw e;
      }
    },
  };

  // Demo-only controls for the mock world (time-skip).
  const DemoRepository = {
    async skipDays(days) {
      const res = await fetch("/mock/clock", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ advance_days: days }),
      });
      if (!res.ok) throw new ApiError(res.status, "Time-skip failed");
      return res.json();
    },
    /** name: "bank_outage" | "late_debit" (spec 17 optional demo moments). */
    async scenario(name) {
      const res = await fetch("/mock/scenario", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new ApiError(res.status, "Scenario failed");
      return res.json();
    },
  };

  Object.assign(window, {
    BRAND, formatPaise, formatWhen, formatFull, formatDay, STATUS_LABEL, t, I18N, UI_LANGS, getUiLang, setUiLang,
    ApiError, TransactionRepository, AgentRepository, PendingPayments, DemoRepository, ReviewRepository,
    ConfigRepository, PendingVoice, PendingScan, PendingInvestigation, Prefs, VOICE, LANG_TAG,
  });
})();
