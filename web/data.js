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

  async function api(method, path, body, { idempotent = false, retried = false } = {}) {
    await ensureSession();
    const headers = { Authorization: `Bearer ${token}` };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (idempotent) headers["Idempotency-Key"] = newKey();
    const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    if (res.status === 401 && !retried) {
      await ensureSession(true);
      return api(method, path, body, { idempotent, retried: true });
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
  });
})();
