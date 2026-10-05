/*
 * app.js: screens and router. No framework, no build step.
 *
 * Components are plain render functions that take a props object and return an HTML string.
 * All dynamic text goes through esc(). The backend decides everything about a failed payment;
 * this file only shows what it returns (status lines, replies, chips, actions).
 */
(function () {
  "use strict";

  const $app = document.getElementById("app");
  document.title = `${BRAND.appName} ${BRAND.assistantName}`;

  // ------------------------------------------------------------------ helpers
  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function initials(name) {
    return esc((name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase());
  }
  function goBack(fallback) {
    if (history.length > 1) history.back();
    else location.hash = fallback || "#/";
  }

  const Icon = {
    back: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>',
    mic: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/></svg>',
    micSmall: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5"/></svg>',
    send: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
    check: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>',
    cross: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>',
    clock: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    keyboard: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/></svg>',
    close: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>',
    speaker: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>',
    speakerOff: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M23 9l-6 6M17 9l6 6"/></svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
    scan: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 7V3h4M17 3h4v4M21 17v4h-4M7 21H3v-4M3 12h18"/></svg>',
    phone: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="2"/><path d="M11 18h2"/></svg>',
    bank: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 10l9-6 9 6M5 10v8M19 10v8M9 10v8M15 10v8M3 20h18"/></svg>',
    spark: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z"/><path d="M19 15l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/></svg>',
    tick: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>',
    rules: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z"/></svg>',
    followup: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/></svg>',
    wallet: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M16 13h2M2 10h20"/></svg>',
  };

  // Labels in the UI language (looked up when used, so the language toggle applies at once).
  const HEADLINE = new Proxy({}, { get: (_o, status) => t("h" + String(status)) });
  const MIC_HINT = new Proxy({}, { get: (_o, status) => t("mic" + String(status)) });
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /** Only failed or pending outgoing payments get the AI mic button. */
  function needsHelp(txn) {
    return txn.direction === "OUT" && (txn.status === "FAILED" || txn.status === "PENDING");
  }

  // ------------------------------------------------------------------ components

  /** LangToggle: the UI language, which is also the language the agent answers in. props: {} */
  function LangToggle() {
    const current = getUiLang();
    return `<div class="lang-toggle" role="group" aria-label="${esc(t("language"))}">${UI_LANGS.map(([lang, label]) =>
      `<button type="button" class="lang-toggle__btn" data-lang="${lang}" lang="${lang}" aria-pressed="${lang === current}">${label}</button>`).join("")}</div>`;
  }

  /** AppHeader. props: { title, subtitle?, back?: boolean, brand?: boolean, right?: html, lang?: boolean } */
  function AppHeader({ title, subtitle, back, brand, right, lang = true }) {
    return `
      <header class="app-header ${brand ? "app-header--brand" : ""}">
        ${back ? `<button class="app-header__back" data-action="back" aria-label="${esc(t("back"))}">${Icon.back}</button>` : ""}
        <div class="app-header__titles">
          <h1 class="app-header__title">${title}</h1>
          ${subtitle ? `<p class="app-header__subtitle">${esc(subtitle)}</p>` : ""}
        </div>
        ${lang ? LangToggle() : ""}
        ${right || ""}
      </header>`;
  }

  /** StatusPill. props: { status: "SUCCESS" | "FAILED" | "PENDING" } */
  function StatusPill({ status }) {
    return `<span class="pill pill--${esc(status)}">${esc(STATUS_LABEL[status] || status)}</span>`;
  }

  /** TxnRow. props: { txn } (transaction shape from TransactionRepository) */
  function TxnRow({ txn }) {
    const incoming = txn.direction === "IN";
    const badge = txn.case && txn.case.hasUpdate ? '<span class="avatar__badge" title="${esc(t("newUpdate"))}"></span>' : "";
    return `
      <a class="txn-row" href="#/txn/${encodeURIComponent(txn.id)}">
        <span class="avatar">${initials(txn.payeeName)}${badge}</span>
        <span class="txn-row__main">
          <div class="txn-row__name">${esc(incoming ? t("receivedFrom", { name: txn.payeeName }) : txn.payeeName)}</div>
          <div class="txn-row__meta">${esc(formatWhen(txn.timestamp))}</div>
          ${txn.case && txn.case.statusLine ? `<div class="txn-row__case">${esc(txn.case.statusLine)}</div>` : ""}
        </span>
        <span class="txn-row__side">
          <div class="txn-row__amount ${incoming ? "txn-row__amount--in" : ""}">${incoming ? "+" : "-"}${esc(formatPaise(txn.amountPaise))}</div>
          ${txn.status !== "SUCCESS" ? StatusPill({ status: txn.status }) : ""}
        </span>
      </a>`;
  }

  /** TxnList. props: { txns } */
  function TxnList({ txns }) {
    if (!txns.length) return `<div class="state">${esc(t("noPayments"))}</div>`;
    return `<div class="txn-list">${txns.map((t) => TxnRow({ txn: t })).join("")}</div>`;
  }

  /** MicButton: the floating AI mic, bound to one payment. props: { txnId, hint } */
  function MicButton({ txnId, hint }) {
    return `
      <div class="mic-dock">
        <span class="mic-dock__hint">${esc(hint)}</span>
        <button class="mic-fab" data-mic-txn="${esc(txnId)}" aria-label="${esc(hint)}: ${esc(t("talkTo", { name: BRAND.assistantName }))}">${Icon.mic}</button>
      </div>`;
  }

  /** CaseCard: pinned at the top of the chat. props: { card } (case.card from the API) */
  function CaseCard({ card }) {
    return `
      <section class="case-card" aria-label="Payment this chat is about">
        <div>
          <div class="case-card__payee">${esc(card.payeeName)}</div>
          <div class="muted">${esc(formatWhen(card.timestamp))}</div>
        </div>
        <div>
          <div class="case-card__amount">${esc(formatPaise(card.amountPaise))}</div>
          <div style="text-align:right">${StatusPill({ status: card.status })}</div>
        </div>
        ${card.statusLine ? `<div class="case-card__line">${esc(card.statusLine)}</div>` : ""}
        ${card.nextAction ? `<div class="case-card__next">${esc(t("next"))}: ${esc(card.nextAction)}${card.expectedBy ? ` · ${esc(t("expectedBy", { date: formatDay(card.expectedBy) }))}` : ""}</div>` : ""}
      </section>`;
  }

  /** ChatBubble. props: { message: {id?, role, kind, text, ts?}, pending?: boolean,
   *  shownText?: string } (shownText: the part of a reply revealed so far, in step with the voice) */
  function ChatBubble({ message, pending, shownText }) {
    const isUser = message.role === "user";
    const isUpdate = message.kind === "update";
    const cls = isUser ? "bubble--user" : `bubble--agent ${isUpdate ? "bubble--update" : ""}`;
    const text = shownText === undefined ? message.text : shownText;
    return `
      <div class="bubble ${cls} ${pending ? "bubble--pending" : ""}" lang="${esc(message.lang || "")}" ${message.id ? `data-msg-id="${esc(message.id)}"` : ""}>
        ${isUpdate ? `<span class="bubble__tag">${esc(t("update"))}</span>` : ""}<span class="bubble__text">${esc(text)}</span>
        ${message.ts ? `<span class="bubble__time">${esc(formatWhen(message.ts))}</span>` : ""}
      </div>`;
  }

  /** Chips: action chips under the newest agent reply. props: { chips: [{id, label}], disabled } */
  function Chips({ chips, disabled }) {
    if (!chips || !chips.length) return "";
    return `<div class="chips">${chips.map((c) => `
      <button class="chip ${c.id === "retry" ? "chip--primary" : ""}" data-chip="${esc(c.id)}" data-label="${esc(c.label)}" ${disabled ? "disabled" : ""}>${esc(c.label)}</button>`).join("")}
    </div>`;
  }

  /** ThinkingDots. props: {} */
  function ThinkingDots() {
    return `<div class="thinking" role="status" aria-label="${esc(t("thinking"))}"><span></span><span></span><span></span></div>`;
  }

  /** ChatEmptyHint: shown before the first message. props: { voice: boolean } */
  function ChatEmptyHint({ voice }) {
    const examples = ["Did my money get cut?", "paise kat gaye par mila nahi", "माझे पैसे कापले का?"];
    return `
      <div class="chat__hint">
        <strong>${esc(t("askTitle"))}</strong>
        ${esc(voice ? t("askVoice") : t("askText"))}
        <div class="chat__examples">${examples.map((e) => `<button class="chip" data-example="${esc(e)}">${esc(e)}</button>`).join("")}</div>
      </div>`;
  }

  /** Composer: mic (voice-first) + text input fallback. props: { disabled, voice: boolean } */
  function Composer({ disabled, voice }) {
    const micLabel = esc(voice ? t("speak") : t("voiceOff"));
    return `
      <form class="composer" data-form="composer" autocomplete="off">
        <button type="button" class="icon-btn ${voice ? "" : "icon-btn--ghost"}" data-action="mic" title="${micLabel}" aria-label="${micLabel}" ${disabled ? "disabled" : ""}>${Icon.micSmall}</button>
        <input class="composer__input" name="text" placeholder="${esc(t("typeQuestion"))}" aria-label="${esc(t("yourMessage"))}" maxlength="500" ${disabled ? "disabled" : ""}>
        <button type="submit" class="icon-btn" aria-label="${esc(t("send"))}" ${disabled ? "disabled" : ""}>${Icon.send}</button>
      </form>`;
  }

  /** Loading. props: { label } */
  function Loading({ label }) {
    return `<div class="state" role="status"><div class="spinner"></div>${esc(label || t("loading"))}</div>`;
  }

  /** ErrorState. props: { message } */
  function ErrorState({ message }) {
    return `<div class="state state--error">${esc(message)}<br><button class="btn-link" data-action="reload">${esc(t("tryAgain"))}</button></div>`;
  }

  const AGENT_ICON = { bank: Icon.bank, rules: Icon.rules, followup: Icon.followup };

  /** InvestigationPanel: the agents' work right after a payment fails, Grok-style. The lines come
   *  from the backend (real evidence, rules and re-check, in the UI language).
   *  props: { agents: [{id, name, lines, tone, verdict}], progress: {agent, lines, done} | null }
   *  (progress: the live animation; null = an earlier investigation, shown collapsed) */
  function InvestigationPanel({ agents, progress }) {
    const live = !!(progress && !progress.done);
    const visible = live ? agents.slice(0, progress.agent + 1) : agents;
    return `
      <details class="inv ${live ? "inv--live" : ""}" ${progress ? "open" : ""}>
        <summary class="inv__head">
          <span class="inv__spark">${Icon.spark}</span>
          <span class="inv__title">${esc(t("invTitle"))}</span>
          <span class="inv__count">${live ? `${progress.agent}/${agents.length}` : esc(t("invAgents", { n: agents.length }))}</span>
        </summary>
        <ol class="inv__list">
          ${visible.map((a, i) => {
            const active = live && i === progress.agent;
            const lines = active ? a.lines.slice(0, progress.lines) : a.lines;
            const badge = active
              ? `<span class="agent__thinking">${esc(t("agentThinking"))}<span class="agent__dots"><span></span><span></span><span></span></span></span>`
              : a.verdict ? `<span class="agent__verdict agent__verdict--${esc(a.tone)}">${esc(a.verdict)}</span>`
                : `<span class="agent__check">${Icon.tick}</span>`;
            return `
            <li class="agent agent--${esc(a.id)} ${active ? "agent--active" : ""}">
              <span class="agent__avatar">${AGENT_ICON[a.id] || ""}</span>
              <div class="agent__body">
                <div class="agent__top"><span class="agent__name">${esc(a.name)}</span>${badge}</div>
                <ul class="agent__lines">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
              </div>
            </li>`;
          }).join("")}
        </ol>
      </details>`;
  }

  /** "+919876543210" -> "+91 98765 43210" */
  function formatPhone(phone) {
    const m = /^\+91(\d{5})(\d{5})$/.exec(phone || "");
    return m ? `+91 ${m[1]} ${m[2]}` : phone;
  }

  /** CallCard: under the agent's "connecting you" reply; also the fallback if the dialer didn't open.
   *  props: { phone } */
  function CallCard({ phone }) {
    return `
      <a class="call-card" href="tel:${esc(phone)}">
        <span class="call-card__icon">${Icon.phone}</span>
        <span class="call-card__main"><span class="call-card__title">${esc(t("callTitle"))}</span>
          <span class="call-card__number">${esc(formatPhone(phone))}</span></span>
        <span class="call-card__btn">${esc(t("callNow"))}</span>
      </a>`;
  }

  /** Ring a number: opens the phone's dialer (the native app shell hands tel: links to Android). */
  function ringPhone(phone) {
    window.location.href = `tel:${phone}`;
  }

  /** KeyValue. props: { k, v } */
  function KeyValue({ k, v }) {
    return v ? `<div class="kv"><span class="kv__k">${esc(k)}</span><span class="kv__v">${esc(v)}</span></div>` : "";
  }

  // ------------------------------------------------------------------ screens
  // Each screen gets (params, isCurrent). isCurrent() turns false when the user navigates away
  // while a request is in flight, so stale responses never paint over the new screen.

  async function HomeScreen(_params, isCurrent) {
    const header = AppHeader({
      brand: true,
      title: `<span class="brand-mark">${esc(BRAND.appName)}</span>`,
      subtitle: t("prototype"),
    });
    $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: t("loadingPayments") })}</div></div>`;
    let txns;
    try {
      txns = await TransactionRepository.list();
    } catch (e) {
      if (isCurrent()) $app.querySelector(".screen__body").innerHTML = ErrorState({ message: e.message });
      return;
    }
    if (!isCurrent()) return;
    // Only Scan & Pay is live in the prototype (it starts the demo's failed payment).
    const tiles = [[t("scanPay"), Icon.scan, "#/scan"], [t("toMobile"), Icon.phone], [t("toBank"), Icon.bank], [t("balance"), Icon.wallet]];
    $app.innerHTML = `
      <div class="screen">
        ${header}
        <div class="screen__body">
          <div class="card">
            <div class="tiles">${tiles.map(([label, icon, href]) => href
              ? `<a class="tile tile--live" href="${href}"><span class="tile__icon">${icon}</span>${esc(label)}</a>`
              : `<span class="tile" aria-disabled="true"><span class="tile__icon">${icon}</span>${esc(label)}</span>`).join("")}</div>
          </div>
          <div class="section-title">${esc(t("recent"))} <a href="#/history">${esc(t("seeAll"))}</a></div>
          ${TxnList({ txns: txns.slice(0, 7) })}
          <div class="demo-tools">
            ${esc(t("demoTools"))}
            <button class="btn btn--secondary" data-action="skip-day">${esc(t("skipDay"))}</button>
          </div>
        </div>
      </div>`;
  }

  async function HistoryScreen(_params, isCurrent) {
    const header = AppHeader({ title: esc(t("history")), back: true });
    $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: t("loadingPayments") })}</div></div>`;
    let txns;
    try {
      txns = await TransactionRepository.list();
    } catch (e) {
      if (isCurrent()) $app.querySelector(".screen__body").innerHTML = ErrorState({ message: e.message });
      return;
    }
    if (!isCurrent()) return;
    // Mic on history opens the most urgent open case: one with an update first, then the newest failure.
    const open = txns.filter((t) => t.case && ["WAITING", "RETRY_OFFERED", "DISPUTED"].includes(t.case.state));
    const urgent = open.find((t) => t.case.hasUpdate) || open[0];
    $app.innerHTML = `
      <div class="screen">
        ${header}
        <div class="screen__body">${TxnList({ txns })}</div>
        ${urgent ? MicButton({ txnId: urgent.id, hint: t("askAbout", { name: urgent.payeeName }) }) : ""}
      </div>`;
  }

  async function TxnScreen({ id }, isCurrent) {
    const header = AppHeader({ title: esc(t("txnDetails")), back: true });
    $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: t("loadingPayment") })}</div></div>`;
    let txn;
    try {
      txn = await TransactionRepository.get(id);
    } catch (e) {
      if (isCurrent()) $app.querySelector(".screen__body").innerHTML = ErrorState({ message: e.status === 404 ? t("notFound") : e.message });
      return;
    }
    if (!isCurrent()) return;
    const icon = { SUCCESS: Icon.check, FAILED: Icon.cross, PENDING: Icon.clock }[txn.status];
    const incoming = txn.direction === "IN";
    $app.innerHTML = `
      <div class="screen">
        ${header}
        <div class="screen__body">
          <div class="card txn-hero">
            <span class="txn-hero__icon txn-hero__icon--${esc(txn.status)}">${icon}</span>
            <p class="txn-hero__headline">${esc(incoming ? t("moneyReceived") : HEADLINE[txn.status])}</p>
            <div class="txn-hero__amount">${esc(formatPaise(txn.amountPaise))}</div>
            <p class="txn-hero__payee">${esc(incoming ? t("from") : t("to"))} <strong>${esc(txn.payeeName)}</strong></p>
          </div>
          ${txn.case && txn.case.statusLine ? `<div class="case-line">${Icon.info}<span>${esc(txn.case.statusLine)}</span></div>` : ""}
          <div class="card">
            ${KeyValue({ k: incoming ? t("fromUpi") : t("toUpi"), v: txn.payeeVpa })}
            ${KeyValue({ k: t("dateTime"), v: formatFull(txn.timestamp) })}
            ${KeyValue({ k: t("upiRef"), v: txn.upiRef })}
            ${KeyValue({ k: t("paidVia"), v: txn.railLabel })}
            ${KeyValue({ k: t("note"), v: txn.note })}
            ${KeyValue({ k: t("reason"), v: txn.failureReason })}
          </div>
        </div>
        ${needsHelp(txn) ? MicButton({ txnId: txn.id, hint: MIC_HINT[txn.status] }) : ""}
      </div>`;
  }

  /** VoiceBar: replaces the composer during a hands-free conversation.
   *  props: { phase: "listening" | "thinking" | "speaking", live: string } */
  function VoiceBar({ phase, live }) {
    const status = { listening: t("listening"), thinking: t("thinking"), speaking: t("speaking") }[phase] || "";
    const orbLabel = esc(phase === "speaking" ? t("orbInterrupt") : phase === "listening" ? t("orbSend") : t("working"));
    return `
      <div class="voicebar voicebar--${esc(phase)}" role="group" aria-label="Voice conversation">
        <button type="button" class="orb orb--small" data-action="orb" data-orb aria-label="${orbLabel}" ${phase === "thinking" ? "disabled" : ""}>
          <span class="orb__core">${Icon.micSmall}</span>
        </button>
        <div class="voicebar__main">
          <div class="voicebar__status">${status}</div>
          <div class="voicebar__live" data-live>${esc(live)}</div>
        </div>
        <button type="button" class="icon-btn icon-btn--ghost" data-action="keyboard" aria-label="${esc(t("typeInstead"))}">${Icon.keyboard}</button>
        <button type="button" class="icon-btn icon-btn--ghost" data-action="end-voice" aria-label="${esc(t("endVoice"))}">${Icon.close}</button>
      </div>`;
  }

  async function AgentScreen({ id: txnId }, isCurrent) {
    let health = await ConfigRepository.health();
    let voice = !!(health.stt && Voice.supported);
    const headerFor = (muted) => AppHeader({
      title: esc(BRAND.assistantName), subtitle: `${t("aboutPayment")}${voice ? "" : ` · ${t("textMode")}`}`, back: true,
      right: health.tts
        ? `<button class="app-header__back" data-action="mute" aria-pressed="${muted}" aria-label="${esc(muted ? t("unmute") : t("mute"))}">${muted ? Icon.speakerOff : Icon.speaker}</button>`
        : "",
    });
    $app.innerHTML = `<div class="screen screen--chat">${headerFor(Prefs.muted)}<div class="chat">${ThinkingDots()}</div>${Composer({ disabled: true, voice })}</div>`;

    // Arrived straight from a payment that just failed: the agents' investigation plays first.
    const investigate = PendingInvestigation.take(txnId);
    let opened;
    try {
      opened = await AgentRepository.openCase(txnId, { investigate });
    } catch (e) {
      if (isCurrent()) $app.querySelector(".chat").innerHTML = ErrorState({ message: e.message });
      return;
    }
    if (!isCurrent()) return;

    const state = {
      caseId: opened.case.id, card: opened.case.card, messages: opened.messages,
      busy: false, pending: null, error: null, notice: null, muted: Prefs.muted,
      revealing: null, // { id, tokens, shown }: the newest reply, revealed in step with its voice
      inv: null, // { msgId, agent, lines, done }: the live investigation animation
      held: new Set(), // message ids not shown yet (the conclusion, until the agents finish)
    };
    // Hands-free conversation (Siri-style): listen -> reply is spoken -> listen again, until the
    // user is silent, says thanks, taps stop, or the reply ends the conversation.
    const convo = { active: false, phase: "idle", ctrl: null, live: "", chip: null, endAfterSpeech: false };
    screenCleanup = () => { convo.active = false; if (convo.ctrl) convo.ctrl.cancel(); };

    function paint() {
      if (!isCurrent()) return;
      const rev = state.revealing;
      const shown = state.messages.filter((m) => !state.held.has(m.id));
      const lastAgent = shown.map((m) => m.role).lastIndexOf("agent");
      const lastIsAgent = lastAgent === shown.length - 1;
      const investigating = !!(state.inv && !state.inv.done);
      const showChips = !state.pending && !rev && !investigating; // chips only once the reply has finished
      const body = shown.map((m, i) => {
        const inv = (m.actions || []).find((a) => a.type === "INVESTIGATION");
        const call = (m.actions || []).find((a) => a.type === "CALL_HUMAN");
        const panel = (inv ? InvestigationPanel({ agents: inv.agents, progress: state.inv && state.inv.msgId === m.id ? state.inv : null }) : "")
          + (call && !(rev && m.id === rev.id) ? CallCard({ phone: call.phone }) : "");
        if (rev && m.id === rev.id) {
          // not started speaking yet -> "thinking" dots; then the words appear as they are spoken
          return (rev.shown === 0 ? ThinkingDots() : ChatBubble({ message: m, shownText: rev.tokens.slice(0, rev.shown).join("") })) + panel;
        }
        return ChatBubble({ message: m }) + panel +
          (i === lastAgent && lastIsAgent && showChips ? Chips({ chips: m.chips, disabled: state.busy }) : "");
      }).join("");
      const liveBubble = convo.active && convo.phase === "listening" && convo.live
        ? ChatBubble({ message: { role: "user", text: convo.live }, pending: true }).replace('class="bubble', 'data-live-bubble class="bubble')
        : "";
      const input = $app.querySelector(".composer__input");
      const draft = input && !state.busy ? input.value : "";
      $app.innerHTML = `
        <div class="screen screen--chat">
          ${headerFor(state.muted)}
          ${CaseCard({ card: state.card })}
          <div class="chat" id="chat" aria-live="polite">
            ${!state.messages.length && !state.pending && !liveBubble ? ChatEmptyHint({ voice }) : ""}
            ${body}
            ${liveBubble}
            ${state.pending ? ChatBubble({ message: { role: "user", text: state.pending }, pending: true }) : ""}
            ${state.busy ? ThinkingDots() : ""}
          </div>
          ${state.error ? `<div class="error-line" role="alert">${esc(state.error)}</div>` : ""}
          ${state.notice && !state.error ? `<div class="notice-line">${esc(state.notice)}</div>` : ""}
          ${convo.active ? VoiceBar({ phase: convo.phase, live: convo.live }) : Composer({ disabled: state.busy || investigating, voice })}
        </div>`;
      scrollChat();
      const newInput = $app.querySelector(".composer__input");
      if (newInput && draft) newInput.value = draft;
      if (newInput && !state.busy && !voice) newInput.focus(); // voice-first: don't pop the keyboard
    }
    const scrollChat = () => { const c = $app.querySelector("#chat"); if (c) c.scrollTop = c.scrollHeight; };
    const setOrb = (lvl) => { const o = $app.querySelector("[data-orb]"); if (o) o.style.setProperty("--level", lvl.toFixed(3)); };
    /** The user's words appear in the chat while they talk (browser preview; Sarvam's text replaces it). */
    const setLive = (t) => {
      const hadText = !!convo.live;
      convo.live = t;
      const l = $app.querySelector("[data-live]");
      if (l) l.textContent = t;
      const b = $app.querySelector("[data-live-bubble] .bubble__text");
      if (b) { b.textContent = t; scrollChat(); } else if (!hadText && t) paint();
    };

    /** Reveal the newest reply word by word, following its audio (or a quick typing pace when muted).
     *  Resolves when the whole reply is shown and the voice has finished or was interrupted. */
    async function presentReply(msg, audioUrl) {
      const rev = { id: msg.id, tokens: msg.text.match(/\S+\s*/g) || [msg.text], shown: 0 };
      state.revealing = rev;
      paint();
      const show = (n) => {
        if (state.revealing !== rev || !isCurrent()) return;
        n = Math.max(0, Math.min(rev.tokens.length, n));
        if (n === rev.shown) return;
        const first = rev.shown === 0;
        rev.shown = n;
        if (first) { paint(); return; } // swap the thinking dots for the bubble
        const el = $app.querySelector(`[data-msg-id="${msg.id}"] .bubble__text`);
        if (el) { el.textContent = rev.tokens.slice(0, n).join(""); scrollChat(); }
      };
      let outcome = "none";
      if (audioUrl && !state.muted) {
        // a word appears just before it is spoken
        outcome = await playAudio(audioUrl, (f) => show(Math.ceil(f * rev.tokens.length + 0.5)));
      }
      if (outcome === "none" || outcome === "failed") {
        // no voice to follow: type the reply out at reading pace
        while (state.revealing === rev && rev.shown < rev.tokens.length && isCurrent()) {
          show(rev.shown + 1);
          await new Promise((r) => setTimeout(r, VOICE.wordMs));
        }
      }
      show(rev.tokens.length); // ended or interrupted: show everything
      if (state.revealing === rev) { state.revealing = null; paint(); }
    }

    function voiceError(e) {
      const detail = e && e.detail;
      if (e && e.status === 422 && detail === "no_speech") return t("didntCatch");
      if (e && e.status === 422 && String(detail).startsWith("stt_disabled")) return t("voiceOff");
      if (e && e.status === 502) return t("voiceUnavailable");
      return t("couldntSend", { msg: e ? e.message : "?" });
    }

    /** One turn. input: { text } | { chipId, label } | { audio: {blob, liveText} }.
     *  Returns { res, playing } (playing resolves when the reply has been spoken and shown),
     *  { noSpeech: true } when the audio had no words, or null on any other error. */
    async function send(input, { quietNoSpeech = false } = {}) {
      if (state.busy) return null;
      const { text, chipId, label, audio } = input;
      stopAudio();
      state.busy = true;
      state.error = null;
      state.notice = null;
      state.pending = text || label || (audio && (audio.liveText || "🎤 …"));
      convo.live = "";
      paint();
      try {
        let res;
        if (chipId === "retry") res = await AgentRepository.confirmRetry(state.caseId);
        else if (audio) res = await AgentRepository.sendVoice(state.caseId, audio.blob, { lang: Prefs.lastLang });
        else res = await AgentRepository.sendTurn(state.caseId, { text, chipId });
        state.card = res.case.card;
        Prefs.lastLang = res.lang;
        const [userMsg, agentMsg] = res.messages;
        state.messages.push(userMsg, agentMsg);
        state.busy = false;
        state.pending = null;
        const playing = presentReply(agentMsg, res.speak && res.speak.audio_url);
        const call = (res.actions || []).find((a) => a.type === "CALL_HUMAN");
        if (call) {
          // "Talk to a human": say "connecting you…", then ring the support line.
          playing.then(() => { if (isCurrent()) ringPhone(call.phone); });
        }
        const pay = (res.actions || []).find((a) => a.type === "OPEN_PAY_SCREEN");
        if (pay) {
          // Let the read-back finish ("Paying ₹350 to …") before the pay screen opens.
          PendingPayments.set(state.caseId, pay.payload);
          Promise.all([playing, new Promise((r) => setTimeout(r, 1500))]).then(() => {
            if (isCurrent()) location.hash = `#/pay/${encodeURIComponent(state.caseId)}`;
          });
        }
        return { res, playing };
      } catch (e) {
        const noSpeech = !!(audio && e && e.status === 422 && e.detail === "no_speech");
        if (!(noSpeech && quietNoSpeech)) state.error = audio ? voiceError(e) : t("couldntSend", { msg: e.message });
        return noSpeech ? { noSpeech: true } : null;
      } finally {
        state.busy = false;
        state.pending = null;
        if (!state.revealing) paint();
      }
    }

    function endConversation(notice) {
      convo.active = false;
      if (convo.ctrl) convo.ctrl.cancel();
      stopAudio();
      if (notice) state.notice = notice;
    }

    /** The hands-free loop. `first` is an already-recorded turn (from the payment screen's sheet). */
    async function converse(first) {
      if (convo.active || !voice) return;
      convo.active = true;
      convo.endAfterSpeech = false;
      state.error = null;
      state.notice = null;
      let next = first || null;
      let misses = 0; // "didn't catch that" in a row
      while (convo.active && isCurrent()) {
        let input = next || convo.chip;
        next = null;
        convo.chip = null;
        if (!input) {
          convo.phase = "listening";
          convo.live = "";
          paint();
          await new Promise((r) => setTimeout(r, 300)); // let the speaker's tail die down (echo)
          if (!convo.active || !isCurrent()) break;
          convo.ctrl = Voice.capture({ lang: Prefs.lastLang, onLevel: setOrb, onText: setLive });
          const r = await convo.ctrl.done;
          convo.ctrl = null;
          if (!convo.active || !isCurrent()) break;
          if (convo.chip) { input = convo.chip; convo.chip = null; } // a chip was tapped while listening
          else if (!r) break;
          else if (r.error) { state.error = r.error; break; }
          else if (r.timeout) { state.notice = t("voicePaused"); break; }
          else input = { audio: r };
        }
        convo.phase = "thinking";
        paint();
        const out = await send(input, { quietNoSpeech: true });
        if (out && out.noSpeech) {
          // Noise, not words: keep the conversation going instead of stopping.
          misses += 1;
          if (misses >= VOICE.maxMisses) { state.notice = t("couldntHear"); break; }
          state.notice = t("sayAgain");
          continue;
        }
        if (!out || !convo.active || !isCurrent()) break;
        misses = 0;
        if (out.res.end_conversation || !VOICE.handsFree) convo.endAfterSpeech = true;
        convo.phase = "speaking";
        paint();
        await out.playing; // ends when the reply has been spoken, or when the user interrupts
        if (convo.endAfterSpeech) break;
      }
      convo.active = false;
      convo.phase = "idle";
      if (convo.ctrl) { convo.ctrl.cancel(); convo.ctrl = null; }
      if (isCurrent()) paint();
    }

    $app.onsubmit = (ev) => {
      if (!ev.target.matches('[data-form="composer"]')) return;
      ev.preventDefault();
      const input = ev.target.elements.text;
      const text = input.value.trim();
      if (text) { input.value = ""; send({ text }); }
    };
    $app.onclick = (ev) => {
      const chip = ev.target.closest("[data-chip]");
      if (chip) {
        const c = { chipId: chip.dataset.chip, label: chip.dataset.label };
        if (convo.active) {
          if (convo.phase === "thinking") return;
          convo.chip = c; // picked up by the loop
          if (convo.ctrl) convo.ctrl.cancel();
          else stopAudio();
          return;
        }
        return send(c);
      }
      const example = ev.target.closest("[data-example]");
      if (example) return send({ text: example.dataset.example });
      if (ev.target.closest('[data-action="mic"]')) {
        if (!voice && !health.stt && Voice.supported) {
          // The check may have failed while the server was waking up: ask again before giving up.
          return ConfigRepository.health().then((h) => {
            health = h;
            voice = !!h.stt;
            if (voice) { paint(); return converse(); }
            state.error = t("voiceOff");
            paint();
          });
        }
        if (!voice) {
          state.error = health.stt ? t("cantRecord") : t("voiceOff");
          paint();
          return;
        }
        return converse();
      }
      if (ev.target.closest('[data-action="orb"]')) {
        if (convo.phase === "listening" && convo.ctrl) convo.ctrl.stop(); // done talking: send now
        else if (convo.phase === "speaking") stopAudio(); // barge-in: the loop goes straight to listening
        return;
      }
      if (ev.target.closest('[data-action="end-voice"]')) { endConversation(); paint(); return; }
      if (ev.target.closest('[data-action="keyboard"]')) {
        endConversation();
        paint();
        const i = $app.querySelector(".composer__input");
        if (i) i.focus();
        return;
      }
      if (ev.target.closest('[data-action="mute"]')) {
        state.muted = !state.muted;
        Prefs.muted = state.muted;
        if (state.muted) stopAudio();
        paint();
        return;
      }
      if (ev.target.closest('[data-action="back"]')) goBack(`#/txn/${encodeURIComponent(txnId)}`);
    };

    /** The agents appear one by one, each "thinking", then their lines (all from the backend). */
    async function playInvestigation(msgId, agents) {
      state.inv = { msgId, agent: 0, lines: 0, done: false };
      for (let i = 0; i < agents.length; i++) {
        state.inv.agent = i;
        state.inv.lines = 0;
        paint();
        await sleep(VOICE.agentThinkMs);
        for (let j = 1; j <= agents[i].lines.length; j++) {
          if (!isCurrent()) return;
          state.inv.lines = j;
          paint();
          await sleep(VOICE.agentLineMs);
        }
      }
      state.inv.done = true;
      paint();
    }

    if (opened.investigation) {
      // "Your payment failed. I'm running a detailed investigation." (spoken) while the agents work,
      // then the conclusion (spoken), then the normal hands-free conversation.
      const { intro, agents, conclusion } = opened.investigation;
      state.held.add(conclusion.id);
      Promise.all([presentReply(intro, intro.audio_url), playInvestigation(intro.id, agents)]).then(async () => {
        if (!isCurrent()) return;
        state.held.delete(conclusion.id);
        await presentReply(conclusion, conclusion.audio_url);
        if (isCurrent() && voice && !convo.active && !state.busy) converse();
      });
      return;
    }
    paint();

    // Arrived from the mic on the payment screen: the first turn is already recorded; keep talking.
    const handoff = PendingVoice.take(txnId);
    if (handoff && handoff.error) { state.error = handoff.error; paint(); }
    else if (handoff) converse({ audio: handoff });
  }

  async function PayScreen({ caseId }, isCurrent) {
    const payload = PendingPayments.get(caseId);
    const header = AppHeader({ title: esc(t("pay")), subtitle: t("retrySubtitle"), back: true });
    if (!payload) {
      $app.innerHTML = `<div class="screen">${header}<div class="screen__body"><div class="state">${esc(t("noRetry"))}</div></div></div>`;
      return;
    }
    // Payee and amount come only from the backend's retry payload (Paytm record), never from user input.
    $app.innerHTML = `
      <div class="screen">
        ${header}
        <div class="screen__body">
          <div class="card txn-hero">
            <span class="avatar" style="margin:0 auto var(--space-3)">${initials(payload.payee_display || payload.payee_name)}</span>
            <p class="txn-hero__headline">${esc(payload.payee_display || payload.payee_name)}</p>
            <p class="txn-hero__payee">${esc(payload.payee_vpa)}</p>
            <div class="txn-hero__amount">${esc(formatPaise(payload.amount_paise))}</div>
            <p class="muted">${esc(payload.note || "")}</p>
          </div>
          <form class="card" data-form="pin" autocomplete="off">
            <label class="muted" for="pin">${esc(t("enterPin"))}</label>
            <input id="pin" class="pin-input" name="pin" type="password" inputmode="numeric" pattern="[0-9]{4,6}" minlength="4" maxlength="6" required>
            <div class="error-line" data-error></div>
            <button class="btn" type="submit">${esc(t("payAmount", { amount: formatPaise(payload.amount_paise) }))}</button>
          </form>
          <p class="muted center">${esc(t("prototype"))}</p>
        </div>
      </div>`;
    $app.querySelector("#pin").focus();
    $app.onclick = (ev) => { if (ev.target.closest('[data-action="back"]')) goBack("#/"); };
    $app.onsubmit = async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const pin = form.elements.pin.value;
      if (!/^\d{4,6}$/.test(pin)) {
        form.querySelector("[data-error]").textContent = t("pinDigits");
        return;
      }
      form.querySelector("button").disabled = true;
      try {
        const res = await TransactionRepository.pay({ ...payload, pin, retry_of_case_id: caseId });
        PendingPayments.clear(caseId);
        if (!isCurrent()) return;
        $app.innerHTML = `
          <div class="screen">
            ${AppHeader({ title: esc(t("hSUCCESS")) })}
            <div class="screen__body">
              <div class="card txn-hero">
                <span class="txn-hero__icon txn-hero__icon--SUCCESS">${Icon.check}</span>
                <p class="txn-hero__headline">${esc(t("paid"))}</p>
                <div class="txn-hero__amount">${esc(formatPaise(res.transaction.amountPaise))}</div>
                <p class="txn-hero__payee">${esc(t("to"))} <strong>${esc(res.transaction.payeeName)}</strong></p>
              </div>
              <a class="btn" href="#/agent/${encodeURIComponent(payload.retry_of_txn_id)}">${esc(t("backToChat"))}</a>
              <a class="btn btn--secondary" href="#/">${esc(t("home"))}</a>
            </div>
          </div>`;
      } catch (e) {
        form.querySelector("button").disabled = false;
        form.querySelector("[data-error]").textContent = e.message;
      }
    };
  }

  // ------------------------------------------------------------------ Scan & Pay (demo: the payment fails)

  /** Scanner: a mock viewfinder. A merchant QR is "found" after a moment (the backend decodes it). */
  async function ScanScreen(_params, isCurrent) {
    $app.innerHTML = `
      <div class="screen screen--scan">
        ${AppHeader({ title: esc(t("scanTitle")), subtitle: t("scanSub"), back: true })}
        <div class="scanner">
          <div class="scanner__frame" aria-hidden="true"><span class="scanner__line"></span></div>
          <p class="scanner__hint" data-scan-status>${esc(t("pointCamera"))}</p>
        </div>
      </div>`;
    await new Promise((r) => setTimeout(r, 1600));
    if (!isCurrent()) return;
    try {
      const qr = await TransactionRepository.scan();
      if (!isCurrent()) return;
      PendingScan.set(qr);
      location.replace("#/send");
    } catch (e) {
      if (isCurrent()) $app.querySelector("[data-scan-status]").textContent = t("couldntScan", { msg: e.message });
    }
  }

  /** PaymentResult: the outcome card after paying. props: { txn } */
  function PaymentResult({ txn }) {
    const failed = txn.status !== "SUCCESS";
    const icon = { SUCCESS: Icon.check, FAILED: Icon.cross, PENDING: Icon.clock }[txn.status];
    return `
      <div class="card txn-hero">
        <span class="txn-hero__icon txn-hero__icon--${esc(txn.status)}">${icon}</span>
        <p class="txn-hero__headline">${esc(HEADLINE[txn.status])}</p>
        <div class="txn-hero__amount">${esc(formatPaise(txn.amountPaise))}</div>
        <p class="txn-hero__payee">${esc(t("to"))} <strong>${esc(txn.payeeName)}</strong></p>
        ${failed && txn.failureReason ? `<p class="muted">${esc(txn.failureReason)}</p>` : ""}
      </div>
      ${failed ? `<div class="case-line">${Icon.info}<span>${esc(t("investigating", { assistant: BRAND.assistantName }))}</span></div>` : ""}`;
  }

  /** Pay a scanned merchant: amount -> PIN -> result. In the demo the payment fails on purpose
   *  (backend DEMO_SCAN_PAY_FAILURE), and the AI chat opens with the agents' investigation. */
  async function SendScreen(_params, isCurrent) {
    const qr = PendingScan.get();
    const header = AppHeader({ title: esc(t("pay")), subtitle: t("scannedQr"), back: true });
    if (!qr) { location.replace("#/scan"); return; }
    const shownName = qr.payee_display || qr.payee_name; // display only; the payment uses payee_name
    const step = { name: "amount", paise: 0, note: "" };

    function paint(error) {
      if (!isCurrent()) return;
      const payee = `
        <div class="card payee-card">
          <span class="avatar">${initials(shownName)}</span>
          <div><div class="payee-card__name">${esc(shownName)}</div><div class="muted">${esc(qr.payee_vpa)} · ${esc(t("fromQr"))}</div></div>
        </div>`;
      const body = step.name === "amount" ? `
        <form class="card" data-form="amount" autocomplete="off">
          <label class="muted" for="amount">${esc(t("amount"))}</label>
          <div class="amount-field"><span>₹</span><input id="amount" class="amount-input" name="amount" inputmode="decimal" placeholder="0" required></div>
          <input class="composer__input note-input" name="note" placeholder="${esc(t("addNote"))}" maxlength="60">
          <div class="error-line" data-error>${esc(error || "")}</div>
          <button class="btn" type="submit">${esc(t("proceed"))}</button>
        </form>` : `
        <form class="card" data-form="pin" autocomplete="off">
          <p class="muted center">${esc(t("payingTo", { amount: formatPaise(step.paise), payee: shownName }))}</p>
          <label class="muted" for="pin">${esc(t("enterPin"))}</label>
          <input id="pin" class="pin-input" name="pin" type="password" inputmode="numeric" pattern="[0-9]{4,6}" minlength="4" maxlength="6" required>
          <div class="error-line" data-error>${esc(error || "")}</div>
          <button class="btn" type="submit">${esc(t("payAmount", { amount: formatPaise(step.paise) }))}</button>
        </form>`;
      $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${payee}${body}<p class="muted center">${esc(t("prototype"))}</p></div></div>`;
      const first = $app.querySelector("#amount, #pin");
      if (first) first.focus();
    }

    $app.onclick = (ev) => { if (ev.target.closest('[data-action="back"]')) goBack("#/"); };
    $app.onsubmit = async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      if (form.matches('[data-form="amount"]')) {
        const rupees = Number(String(form.elements.amount.value).replace(/[,\s₹]/g, ""));
        if (!(rupees > 0) || rupees > 100000 || !/^\d+(\.\d{1,2})?$/.test(String(rupees))) {
          return paint(t("amountRange"));
        }
        step.paise = Math.round(rupees * 100);
        step.note = form.elements.note.value.trim();
        step.name = "pin";
        return paint();
      }
      const pin = form.elements.pin.value;
      if (!/^\d{4,6}$/.test(pin)) return paint(t("pinDigits"));
      $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: t("paying", { amount: formatPaise(step.paise), payee: shownName }) })}</div></div>`;
      let res;
      try {
        [res] = await Promise.all([
          TransactionRepository.pay({ payee_vpa: qr.payee_vpa, payee_name: qr.payee_name, amount_paise: step.paise,
            note: step.note || null, pin, origin: "scan" }),
          sleep(1200), // a real payment takes a moment
        ]);
      } catch (e) {
        step.name = "pin";
        return paint(e.message);
      }
      if (!isCurrent()) return;
      PendingScan.clear();
      const txn = res.transaction;
      $app.innerHTML = `<div class="screen">${AppHeader({ title: esc(HEADLINE[txn.status]) })}<div class="screen__body">${PaymentResult({ txn })}
        ${txn.status === "SUCCESS" ? `<a class="btn" href="#/">${esc(t("home"))}</a>` : ""}</div></div>`;
      if (needsHelp(txn)) {
        // The failure stays on screen for a moment, then the agent opens and investigates by itself.
        await sleep(1800);
        if (!isCurrent()) return;
        PendingInvestigation.set(txn.id);
        location.replace(`#/agent/${encodeURIComponent(txn.id)}`);
      }
    };
    paint();
  }

  // ------------------------------------------------------------------ audio (TTS)
  const $audio = document.getElementById("tts");
  let finishPlayback = null;

  /** Play a reply. Resolves when it ends, fails, or is interrupted (so a conversation can continue). */
  /** Play a reply. onProgress(0..1) follows playback so the text can be revealed with the voice.
   *  Resolves "ended" | "interrupted" (stopAudio / barge-in) | "failed" (never played) | "none" (no url). */
  function playAudio(url, onProgress = () => {}) {
    stopAudio();
    if (!url || !$audio) return Promise.resolve("none");
    return new Promise((resolve) => {
      let done = false;
      let started = false;
      let raf = 0;
      const fin = (outcome) => {
        if (done) return;
        done = true;
        clearTimeout(guard);
        clearTimeout(loadGuard);
        cancelAnimationFrame(raf);
        $audio.onended = $audio.onerror = $audio.onplaying = $audio.ontimeupdate = null;
        finishPlayback = null;
        if (outcome === "ended") onProgress(1);
        resolve(outcome);
      };
      const report = () => {
        if ($audio.duration > 0 && isFinite($audio.duration)) onProgress($audio.currentTime / $audio.duration);
      };
      const loop = () => { report(); if (!done) raf = requestAnimationFrame(loop); };
      const guard = setTimeout(() => fin(started ? "ended" : "failed"), 60000);
      // Audio that never starts loading (no output device, background tab) must not stall the chat.
      const loadGuard = setTimeout(() => { if (!started) fin("failed"); }, 8000);
      finishPlayback = () => fin(started ? "interrupted" : "failed");
      $audio.onplaying = () => { started = true; loop(); };
      $audio.ontimeupdate = report; // keeps progressing even where animation frames are throttled
      $audio.onended = () => fin("ended");
      $audio.onerror = () => fin("failed");
      $audio.src = url;
      $audio.play().catch(() => fin("failed")); // autoplay blocked: the text is typed out instead
    });
  }
  function stopAudio() {
    if (!$audio) return;
    $audio.pause();
    $audio.removeAttribute("src");
    if (finishPlayback) finishPlayback();
  }

  /** Floating mic on a payment: listen right here (sheet over the screen), then open that payment's chat. */
  async function micForPayment(txnId) {
    const target = `#/agent/${encodeURIComponent(txnId)}`;
    const health = await ConfigRepository.health();
    if (!health.stt || !Voice.supported) { location.hash = target; return; } // text mode
    const r = await Voice.listen({ lang: Prefs.lastLang });
    if (!r || r.timeout) return; // cancelled or nothing said: stay on this screen
    PendingVoice.set(txnId, r);
    location.hash = target;
  }

  // ------------------------------------------------------------------ router
  const routes = [
    [/^#?\/?$/, HomeScreen, []],
    [/^#\/history$/, HistoryScreen, []],
    [/^#\/txn\/([^/]+)$/, TxnScreen, ["id"]],
    [/^#\/agent\/([^/]+)$/, AgentScreen, ["id"]],
    [/^#\/pay\/([^/]+)$/, PayScreen, ["caseId"]],
    [/^#\/scan$/, ScanScreen, []],
    [/^#\/send$/, SendScreen, []],
  ];
  let navSeq = 0;
  let screenCleanup = null; // set by a screen that holds resources (mic) until navigation

  function route() {
    const seq = ++navSeq;
    const isCurrent = () => seq === navSeq;
    if (screenCleanup) { screenCleanup(); screenCleanup = null; } // e.g. turn the mic off when leaving the chat
    stopAudio();
    $app.onclick = defaultClick;
    $app.onsubmit = null;
    const hash = location.hash || "#/";
    for (const [re, screen, names] of routes) {
      const m = hash.match(re);
      if (m) {
        const params = Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(m[i + 1])]));
        window.scrollTo(0, 0);
        screen(params, isCurrent);
        return;
      }
    }
    location.hash = "#/";
  }

  async function defaultClick(ev) {
    const mic = ev.target.closest("[data-mic-txn]");
    if (mic) return micForPayment(mic.dataset.micTxn);
    if (ev.target.closest('[data-action="back"]')) return goBack("#/");
    if (ev.target.closest('[data-action="reload"]')) return route();
    const skip = ev.target.closest('[data-action="skip-day"]');
    if (skip) {
      skip.disabled = true;
      try {
        await DemoRepository.skipDays(1);
      } finally {
        route();
      }
    }
  }

  // Language toggle (in every header). Capture phase: screens replace $app.onclick.
  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-lang]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    if (btn.dataset.lang !== getUiLang()) {
      setUiLang(btn.dataset.lang);
      route(); // repaint in the new language; the agent answers in it from now on
    }
  }, true);

  window.addEventListener("hashchange", route);
  route();
})();
