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

  // ------------------------------------------------------------------ formatters
  const IST = "Asia/Kolkata";
  const timeFmt = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST });
  const dayFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: IST });
  const fullFmt = new Intl.DateTimeFormat("en-IN", {
    day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZone: IST,
  });
  const dateKey = (d) => d.toLocaleDateString("en-CA", { timeZone: IST });

  /** 149900 -> "₹1,499"; 12345 -> "₹123.45" */
  function formatPaise(paise) {
    const rupees = Math.abs(paise) / 100;
    const opts = Number.isInteger(rupees) ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    return (paise < 0 ? "-" : "") + "₹" + rupees.toLocaleString("en-IN", opts);
  }

  /** ISO timestamp -> "Today, 11:19 am" / "Yesterday, 9:15 pm" / "29 Sep, 6:05 pm" */
  function formatWhen(iso) {
    const d = new Date(iso);
    const now = new Date();
    const yesterday = new Date(now.getTime() - 86400000);
    const day = dateKey(d) === dateKey(now) ? "Today" : dateKey(d) === dateKey(yesterday) ? "Yesterday" : dayFmt.format(d);
    return `${day}, ${timeFmt.format(d)}`;
  }

  function formatFull(iso) {
    return fullFmt.format(new Date(iso));
  }

  /** "2026-10-04" -> "4 Oct" */
  function formatDay(isoDate) {
    if (!isoDate) return "";
    return dayFmt.format(new Date(isoDate + "T12:00:00+05:30"));
  }

  const STATUS_LABEL = { SUCCESS: "Successful", FAILED: "Failed", PENDING: "Pending" };

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
    const headers = { Authorization: `Bearer ${token}` };
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
    /** Mock pay screen. A retry must match the confirmed retry payload. */
    async pay({ payee_vpa, payee_name, amount_paise, note, pin, retry_of_case_id }) {
      return api("POST", "/v1/payments", { payee_vpa, payee_name, amount_paise, note, pin, retry_of_case_id }, { idempotent: true });
    },
  };

  const AgentRepository = {
    /** User tapped the mic on this payment: one session per payment. */
    async openCase(txnId) {
      return api("POST", "/v1/cases/open", { txn_id: txnId });
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

  // Small per-viewer conveniences (never business state).
  const Prefs = {
    get muted() { return store.get("pref_muted") === "1"; },
    set muted(v) { store.set("pref_muted", v ? "1" : "0"); },
    get lastLang() { return store.get("pref_lang") || "en"; },
    set lastLang(v) { if (v) store.set("pref_lang", v); },
  };

  /*
   * Voice settings. The live transcript in the listening sheet uses the browser's speech
   * recognizer only as a preview while the user talks (in Chrome that audio is processed by
   * Google); the transcript that counts comes from Sarvam via the backend. Set
   * liveTranscript: false to show only the voice-level orb.
   */
  const VOICE = Object.freeze({
    liveTranscript: true,
    silenceMs: 1500, // end of speech after this much silence (spec 4.2)
    maxMs: 15000,
    speechLevel: 0.04, // RMS above this counts as speech
  });
  const LANG_TAG = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };

  // Demo-only controls for the mock world (time-skip).
  const DemoRepository = {
    async skipDays(days) {
      const res = await fetch("/mock/clock", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ advance_days: days }),
      });
      if (!res.ok) throw new ApiError(res.status, "Time-skip failed");
      return res.json();
    },
  };

  Object.assign(window, {
    BRAND, formatPaise, formatWhen, formatFull, formatDay, STATUS_LABEL,
    ApiError, TransactionRepository, AgentRepository, PendingPayments, DemoRepository,
    ConfigRepository, PendingVoice, Prefs, VOICE, LANG_TAG,
  });
})();
