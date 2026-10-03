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
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
    scan: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 7V3h4M17 3h4v4M21 17v4h-4M7 21H3v-4M3 12h18"/></svg>',
    phone: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="2"/><path d="M11 18h2"/></svg>',
    bank: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 10l9-6 9 6M5 10v8M19 10v8M9 10v8M15 10v8M3 20h18"/></svg>',
    wallet: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M16 13h2M2 10h20"/></svg>',
  };

  const HEADLINE = { SUCCESS: "Payment successful", FAILED: "Payment failed", PENDING: "Payment pending" };
  const MIC_HINT = { FAILED: "Payment failed? Ask me", PENDING: "Payment pending? Ask me" };

  /** Only failed or pending outgoing payments get the AI mic button. */
  function needsHelp(txn) {
    return txn.direction === "OUT" && (txn.status === "FAILED" || txn.status === "PENDING");
  }

  // ------------------------------------------------------------------ components

  /** AppHeader. props: { title, subtitle?, back?: boolean, brand?: boolean, right?: html } */
  function AppHeader({ title, subtitle, back, brand, right }) {
    return `
      <header class="app-header ${brand ? "app-header--brand" : ""}">
        ${back ? `<button class="app-header__back" data-action="back" aria-label="Back">${Icon.back}</button>` : ""}
        <div class="app-header__titles">
          <h1 class="app-header__title">${title}</h1>
          ${subtitle ? `<p class="app-header__subtitle">${esc(subtitle)}</p>` : ""}
        </div>
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
    const badge = txn.case && txn.case.hasUpdate ? '<span class="avatar__badge" title="New update"></span>' : "";
    return `
      <a class="txn-row" href="#/txn/${encodeURIComponent(txn.id)}">
        <span class="avatar">${initials(txn.payeeName)}${badge}</span>
        <span class="txn-row__main">
          <div class="txn-row__name">${incoming ? "Received from " : ""}${esc(txn.payeeName)}</div>
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
    if (!txns.length) return '<div class="state">No payments yet.</div>';
    return `<div class="txn-list">${txns.map((t) => TxnRow({ txn: t })).join("")}</div>`;
  }

  /** MicButton: the floating AI mic, bound to one payment. props: { txnId, hint } */
  function MicButton({ txnId, hint }) {
    return `
      <div class="mic-dock">
        <span class="mic-dock__hint">${esc(hint)}</span>
        <a class="mic-fab" href="#/agent/${encodeURIComponent(txnId)}" aria-label="${esc(hint)}: open ${esc(BRAND.assistantName)}">${Icon.mic}</a>
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
        ${card.nextAction ? `<div class="case-card__next">Next: ${esc(card.nextAction)}${card.expectedBy ? ` · expected by ${esc(formatDay(card.expectedBy))}` : ""}</div>` : ""}
      </section>`;
  }

  /** ChatBubble. props: { message: {role, kind, text, ts?}, pending?: boolean } */
  function ChatBubble({ message, pending }) {
    const isUser = message.role === "user";
    const isUpdate = message.kind === "update";
    const cls = isUser ? "bubble--user" : `bubble--agent ${isUpdate ? "bubble--update" : ""}`;
    return `
      <div class="bubble ${cls} ${pending ? "bubble--pending" : ""}" lang="${esc(message.lang || "")}">
        ${isUpdate ? '<span class="bubble__tag">Update</span>' : ""}<span class="bubble__text">${esc(message.text)}</span>
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
    return '<div class="thinking" role="status" aria-label="Thinking"><span></span><span></span><span></span></div>';
  }

  /** ChatEmptyHint: shown before the first message. props: {} */
  function ChatEmptyHint() {
    const examples = ["Did my money get cut?", "paise kat gaye par mila nahi", "माझे पैसे कापले का?"];
    return `
      <div class="chat__hint">
        <strong>Ask about this payment</strong>
        I already know which payment you mean. Ask in English, हिंदी or मराठी.
        <div class="chat__examples">${examples.map((e) => `<button class="chip" data-example="${esc(e)}">${esc(e)}</button>`).join("")}</div>
      </div>`;
  }

  /** Composer: text input + send, with the mic (voice arrives in build step 7). props: { disabled } */
  function Composer({ disabled }) {
    return `
      <form class="composer" data-form="composer" autocomplete="off">
        <button type="button" class="icon-btn icon-btn--ghost" data-action="mic" title="Voice input comes in a later build. Type for now." aria-label="Voice input (coming soon)">${Icon.micSmall}</button>
        <input class="composer__input" name="text" placeholder="Type your question…" aria-label="Your message" maxlength="500" ${disabled ? "disabled" : ""}>
        <button type="submit" class="icon-btn" aria-label="Send" ${disabled ? "disabled" : ""}>${Icon.send}</button>
      </form>`;
  }

  /** Loading. props: { label } */
  function Loading({ label }) {
    return `<div class="state" role="status"><div class="spinner"></div>${esc(label || "Loading…")}</div>`;
  }

  /** ErrorState. props: { message } */
  function ErrorState({ message }) {
    return `<div class="state state--error">${esc(message)}<br><button class="btn-link" data-action="reload">Try again</button></div>`;
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
      subtitle: BRAND.prototypeLabel,
    });
    $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: "Loading payments…" })}</div></div>`;
    let txns;
    try {
      txns = await TransactionRepository.list();
    } catch (e) {
      if (isCurrent()) $app.querySelector(".screen__body").innerHTML = ErrorState({ message: e.message });
      return;
    }
    if (!isCurrent()) return;
    const tiles = [["Scan & Pay", Icon.scan], ["To Mobile", Icon.phone], ["To Bank", Icon.bank], ["Balance", Icon.wallet]];
    $app.innerHTML = `
      <div class="screen">
        ${header}
        <div class="screen__body">
          <div class="card">
            <div class="tiles">${tiles.map(([label, icon]) => `<span class="tile" aria-disabled="true"><span class="tile__icon">${icon}</span>${label}</span>`).join("")}</div>
          </div>
          <div class="section-title">Recent payments <a href="#/history">See all</a></div>
          ${TxnList({ txns: txns.slice(0, 7) })}
          <div class="demo-tools">
            Demo controls (mock world): move the simulated clock forward so deadlines pass.
            <button class="btn btn--secondary" data-action="skip-day">Skip time +1 day</button>
          </div>
        </div>
      </div>`;
  }

  async function HistoryScreen(_params, isCurrent) {
    const header = AppHeader({ title: "Payment history", back: true });
    $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: "Loading payments…" })}</div></div>`;
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
        ${urgent ? MicButton({ txnId: urgent.id, hint: `Ask about ${urgent.payeeName}` }) : ""}
      </div>`;
  }

  async function TxnScreen({ id }, isCurrent) {
    const header = AppHeader({ title: "Transaction details", back: true });
    $app.innerHTML = `<div class="screen">${header}<div class="screen__body">${Loading({ label: "Loading payment…" })}</div></div>`;
    let txn;
    try {
      txn = await TransactionRepository.get(id);
    } catch (e) {
      if (isCurrent()) $app.querySelector(".screen__body").innerHTML = ErrorState({ message: e.status === 404 ? "Payment not found." : e.message });
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
            <p class="txn-hero__headline">${esc(incoming ? "Money received" : HEADLINE[txn.status])}</p>
            <div class="txn-hero__amount">${esc(formatPaise(txn.amountPaise))}</div>
            <p class="txn-hero__payee">${incoming ? "from" : "to"} <strong>${esc(txn.payeeName)}</strong></p>
          </div>
          ${txn.case && txn.case.statusLine ? `<div class="case-line">${Icon.info}<span>${esc(txn.case.statusLine)}</span></div>` : ""}
          <div class="card">
            ${KeyValue({ k: incoming ? "From UPI ID" : "To UPI ID", v: txn.payeeVpa })}
            ${KeyValue({ k: "Date & time", v: formatFull(txn.timestamp) })}
            ${KeyValue({ k: "UPI Ref No.", v: txn.upiRef })}
            ${KeyValue({ k: "Paid via", v: txn.railLabel })}
            ${KeyValue({ k: "Note", v: txn.note })}
            ${KeyValue({ k: "Reason", v: txn.failureReason })}
          </div>
        </div>
        ${needsHelp(txn) ? MicButton({ txnId: txn.id, hint: MIC_HINT[txn.status] }) : ""}
      </div>`;
  }

  async function AgentScreen({ id: txnId }, isCurrent) {
    const header = AppHeader({ title: esc(BRAND.assistantName), subtitle: "About this payment only · text mode", back: true });
    $app.innerHTML = `<div class="screen screen--chat">${header}<div class="chat">${ThinkingDots()}</div>${Composer({ disabled: true })}</div>`;

    let opened;
    try {
      opened = await AgentRepository.openCase(txnId);
    } catch (e) {
      if (isCurrent()) $app.querySelector(".chat").innerHTML = ErrorState({ message: e.message });
      return;
    }
    if (!isCurrent()) return;

    const state = { caseId: opened.case.id, card: opened.case.card, messages: opened.messages, busy: false, pending: null, error: null };

    function paint() {
      if (!isCurrent()) return;
      const lastAgent = state.messages.map((m) => m.role).lastIndexOf("agent");
      const lastIsAgent = lastAgent === state.messages.length - 1;
      const body = state.messages.map((m, i) => ChatBubble({ message: m }) +
        (i === lastAgent && lastIsAgent && !state.pending ? Chips({ chips: m.chips, disabled: state.busy }) : "")).join("");
      $app.innerHTML = `
        <div class="screen screen--chat">
          ${header}
          ${CaseCard({ card: state.card })}
          <div class="chat" id="chat" aria-live="polite">
            ${!state.messages.length && !state.pending ? ChatEmptyHint() : ""}
            ${body}
            ${state.pending ? ChatBubble({ message: { role: "user", text: state.pending }, pending: true }) : ""}
            ${state.busy ? ThinkingDots() : ""}
          </div>
          ${state.error ? `<div class="error-line">${esc(state.error)}</div>` : ""}
          ${Composer({ disabled: state.busy })}
        </div>`;
      const chat = $app.querySelector("#chat");
      chat.scrollTop = chat.scrollHeight;
      if (!state.busy) $app.querySelector(".composer__input").focus();
    }

    async function send({ text, chipId, label }) {
      if (state.busy) return;
      state.busy = true;
      state.error = null;
      state.pending = text || label;
      paint();
      try {
        const r = chipId === "retry"
          ? await AgentRepository.confirmRetry(state.caseId)
          : await AgentRepository.sendTurn(state.caseId, { text, chipId });
        state.messages.push(...r.messages);
        state.card = r.case.card;
        playAudio(r.speak && r.speak.audio_url);
        const pay = (r.actions || []).find((a) => a.type === "OPEN_PAY_SCREEN");
        if (pay) {
          PendingPayments.set(state.caseId, pay.payload);
          setTimeout(() => { if (isCurrent()) location.hash = `#/pay/${encodeURIComponent(state.caseId)}`; }, 1600);
        }
      } catch (e) {
        state.error = `Couldn't send: ${e.message}`;
      } finally {
        state.busy = false;
        state.pending = null;
        paint();
      }
    }

    $app.onsubmit = (ev) => {
      if (!ev.target.matches('[data-form="composer"]')) return;
      ev.preventDefault();
      const input = ev.target.elements.text;
      const text = input.value.trim();
      if (text) send({ text });
    };
    $app.onclick = (ev) => {
      const chip = ev.target.closest("[data-chip]");
      if (chip) return send({ chipId: chip.dataset.chip, label: chip.dataset.label });
      const example = ev.target.closest("[data-example]");
      if (example) return send({ text: example.dataset.example });
      if (ev.target.closest('[data-action="mic"]')) {
        state.error = "Voice input arrives in a later build. Please type for now.";
        paint();
        return;
      }
      if (ev.target.closest('[data-action="back"]')) goBack(`#/txn/${encodeURIComponent(txnId)}`);
    };
    paint();
  }

  async function PayScreen({ caseId }, isCurrent) {
    const payload = PendingPayments.get(caseId);
    const header = AppHeader({ title: "Pay", subtitle: "Retry of a failed payment", back: true });
    if (!payload) {
      $app.innerHTML = `<div class="screen">${header}<div class="screen__body"><div class="state">No confirmed retry for this payment. Go back to the chat and ask again.</div></div></div>`;
      return;
    }
    // Payee and amount come only from the backend's retry payload (Paytm record), never from user input.
    $app.innerHTML = `
      <div class="screen">
        ${header}
        <div class="screen__body">
          <div class="card txn-hero">
            <span class="avatar" style="margin:0 auto var(--space-3)">${initials(payload.payee_name)}</span>
            <p class="txn-hero__headline">${esc(payload.payee_name)}</p>
            <p class="txn-hero__payee">${esc(payload.payee_vpa)}</p>
            <div class="txn-hero__amount">${esc(formatPaise(payload.amount_paise))}</div>
            <p class="muted">${esc(payload.note || "")}</p>
          </div>
          <form class="card" data-form="pin" autocomplete="off">
            <label class="muted" for="pin">Enter UPI PIN (mock, any 4–6 digits)</label>
            <input id="pin" class="pin-input" name="pin" type="password" inputmode="numeric" pattern="[0-9]{4,6}" minlength="4" maxlength="6" required>
            <div class="error-line" data-error></div>
            <button class="btn" type="submit">Pay ${esc(formatPaise(payload.amount_paise))}</button>
          </form>
          <p class="muted center">${esc(BRAND.prototypeLabel)}</p>
        </div>
      </div>`;
    $app.querySelector("#pin").focus();
    $app.onclick = (ev) => { if (ev.target.closest('[data-action="back"]')) goBack("#/"); };
    $app.onsubmit = async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const pin = form.elements.pin.value;
      if (!/^\d{4,6}$/.test(pin)) {
        form.querySelector("[data-error]").textContent = "PIN must be 4 to 6 digits.";
        return;
      }
      form.querySelector("button").disabled = true;
      try {
        const res = await TransactionRepository.pay({ ...payload, pin, retry_of_case_id: caseId });
        PendingPayments.clear(caseId);
        if (!isCurrent()) return;
        $app.innerHTML = `
          <div class="screen">
            ${AppHeader({ title: "Payment successful" })}
            <div class="screen__body">
              <div class="card txn-hero">
                <span class="txn-hero__icon txn-hero__icon--SUCCESS">${Icon.check}</span>
                <p class="txn-hero__headline">Paid</p>
                <div class="txn-hero__amount">${esc(formatPaise(res.transaction.amountPaise))}</div>
                <p class="txn-hero__payee">to <strong>${esc(res.transaction.payeeName)}</strong></p>
              </div>
              <a class="btn" href="#/agent/${encodeURIComponent(payload.retry_of_txn_id)}">Back to chat</a>
              <a class="btn btn--secondary" href="#/">Home</a>
            </div>
          </div>`;
      } catch (e) {
        form.querySelector("button").disabled = false;
        form.querySelector("[data-error]").textContent = e.message;
      }
    };
  }

  // ------------------------------------------------------------------ audio (TTS)
  const $audio = document.getElementById("tts");
  function playAudio(url) {
    if (!url || !$audio) return;
    $audio.src = url;
    $audio.play().catch(() => { /* autoplay blocked: the bubble text is the same as the speech */ });
  }

  // ------------------------------------------------------------------ router
  const routes = [
    [/^#?\/?$/, HomeScreen, []],
    [/^#\/history$/, HistoryScreen, []],
    [/^#\/txn\/([^/]+)$/, TxnScreen, ["id"]],
    [/^#\/agent\/([^/]+)$/, AgentScreen, ["id"]],
    [/^#\/pay\/([^/]+)$/, PayScreen, ["caseId"]],
  ];
  let navSeq = 0;

  function route() {
    const seq = ++navSeq;
    const isCurrent = () => seq === navSeq;
    if ($audio) $audio.pause();
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

  window.addEventListener("hashchange", route);
  route();
})();
