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
        <button class="mic-fab" data-mic-txn="${esc(txnId)}" aria-label="${esc(hint)}: talk to ${esc(BRAND.assistantName)}">${Icon.mic}</button>
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

  /** ChatBubble. props: { message: {id?, role, kind, text, ts?}, pending?: boolean,
   *  shownText?: string } (shownText: the part of a reply revealed so far, in step with the voice) */
  function ChatBubble({ message, pending, shownText }) {
    const isUser = message.role === "user";
    const isUpdate = message.kind === "update";
    const cls = isUser ? "bubble--user" : `bubble--agent ${isUpdate ? "bubble--update" : ""}`;
    const text = shownText === undefined ? message.text : shownText;
    return `
      <div class="bubble ${cls} ${pending ? "bubble--pending" : ""}" lang="${esc(message.lang || "")}" ${message.id ? `data-msg-id="${esc(message.id)}"` : ""}>
        ${isUpdate ? '<span class="bubble__tag">Update</span>' : ""}<span class="bubble__text">${esc(text)}</span>
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

  /** ChatEmptyHint: shown before the first message. props: { voice: boolean } */
  function ChatEmptyHint({ voice }) {
    const examples = ["Did my money get cut?", "paise kat gaye par mila nahi", "माझे पैसे कापले का?"];
    return `
      <div class="chat__hint">
        <strong>Ask about this payment</strong>
        I already know which payment you mean. ${voice ? "Tap the mic and speak, or type," : "Ask"} in English, हिंदी or मराठी.
        <div class="chat__examples">${examples.map((e) => `<button class="chip" data-example="${esc(e)}">${esc(e)}</button>`).join("")}</div>
      </div>`;
  }

  /** Composer: mic (voice-first) + text input fallback. props: { disabled, voice: boolean } */
  function Composer({ disabled, voice }) {
    const micLabel = voice ? "Speak" : "Voice is off on the server. Please type.";
    return `
      <form class="composer" data-form="composer" autocomplete="off">
        <button type="button" class="icon-btn ${voice ? "" : "icon-btn--ghost"}" data-action="mic" title="${micLabel}" aria-label="${micLabel}" ${disabled ? "disabled" : ""}>${Icon.micSmall}</button>
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

  /** VoiceBar: replaces the composer during a hands-free conversation.
   *  props: { phase: "listening" | "thinking" | "speaking", live: string } */
  function VoiceBar({ phase, live }) {
    const status = {
      listening: "Listening…",
      thinking: "Thinking…",
      speaking: "Speaking… tap the orb to interrupt",
    }[phase] || "";
    const orbLabel = phase === "speaking" ? "Interrupt and speak" : phase === "listening" ? "Done speaking, send now" : "Working";
    return `
      <div class="voicebar voicebar--${esc(phase)}" role="group" aria-label="Voice conversation">
        <button type="button" class="orb orb--small" data-action="orb" data-orb aria-label="${orbLabel}" ${phase === "thinking" ? "disabled" : ""}>
          <span class="orb__core">${Icon.micSmall}</span>
        </button>
        <div class="voicebar__main">
          <div class="voicebar__status">${status}</div>
          <div class="voicebar__live" data-live>${esc(live)}</div>
        </div>
        <button type="button" class="icon-btn icon-btn--ghost" data-action="keyboard" aria-label="Type instead">${Icon.keyboard}</button>
        <button type="button" class="icon-btn icon-btn--ghost" data-action="end-voice" aria-label="End voice conversation">${Icon.close}</button>
      </div>`;
  }

  async function AgentScreen({ id: txnId }, isCurrent) {
    const health = await ConfigRepository.health();
    const voice = !!(health.stt && Voice.supported);
    const subtitle = `About this payment only${voice ? "" : " · text mode"}`;
    const headerFor = (muted) => AppHeader({
      title: esc(BRAND.assistantName), subtitle, back: true,
      right: health.tts
        ? `<button class="app-header__back" data-action="mute" aria-pressed="${muted}" aria-label="${muted ? "Unmute replies" : "Mute replies"}">${muted ? Icon.speakerOff : Icon.speaker}</button>`
        : "",
    });
    $app.innerHTML = `<div class="screen screen--chat">${headerFor(Prefs.muted)}<div class="chat">${ThinkingDots()}</div>${Composer({ disabled: true, voice })}</div>`;

    let opened;
    try {
      opened = await AgentRepository.openCase(txnId);
    } catch (e) {
      if (isCurrent()) $app.querySelector(".chat").innerHTML = ErrorState({ message: e.message });
      return;
    }
    if (!isCurrent()) return;

    const state = {
      caseId: opened.case.id, card: opened.case.card, messages: opened.messages,
      busy: false, pending: null, error: null, notice: null, muted: Prefs.muted,
      revealing: null, // { id, tokens, shown }: the newest reply, revealed in step with its voice
    };
    // Hands-free conversation (Siri-style): listen -> reply is spoken -> listen again, until the
    // user is silent, says thanks, taps stop, or the reply ends the conversation.
    const convo = { active: false, phase: "idle", ctrl: null, live: "", chip: null, endAfterSpeech: false };
    screenCleanup = () => { convo.active = false; if (convo.ctrl) convo.ctrl.cancel(); };

    function paint() {
      if (!isCurrent()) return;
      const rev = state.revealing;
      const lastAgent = state.messages.map((m) => m.role).lastIndexOf("agent");
      const lastIsAgent = lastAgent === state.messages.length - 1;
      const showChips = !state.pending && !rev; // follow-up chips only once the reply has finished
      const body = state.messages.map((m, i) => {
        if (rev && m.id === rev.id) {
          // not started speaking yet -> "thinking" dots; then the words appear as they are spoken
          return rev.shown === 0 ? ThinkingDots() : ChatBubble({ message: m, shownText: rev.tokens.slice(0, rev.shown).join("") });
        }
        return ChatBubble({ message: m }) +
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
          ${convo.active ? VoiceBar({ phase: convo.phase, live: convo.live }) : Composer({ disabled: state.busy, voice })}
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
      if (e && e.status === 422 && detail === "no_speech") return "I didn't catch that. Please say it again, or type.";
      if (e && e.status === 422 && String(detail).startsWith("stt_disabled")) return "Voice is off on the server. Please type.";
      if (e && e.status === 502) return "Voice is unavailable right now. Please type your question.";
      return `Couldn't send: ${e ? e.message : "unknown error"}`;
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
        if (!(noSpeech && quietNoSpeech)) state.error = audio ? voiceError(e) : `Couldn't send: ${e.message}`;
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
          else if (r.timeout) { state.notice = "Voice paused. Tap the mic when you want to talk again."; break; }
          else input = { audio: r };
        }
        convo.phase = "thinking";
        paint();
        const out = await send(input, { quietNoSpeech: true });
        if (out && out.noSpeech) {
          // Noise, not words: keep the conversation going instead of stopping.
          misses += 1;
          if (misses >= VOICE.maxMisses) { state.notice = "I couldn't hear you clearly. Tap the mic to try again, or type."; break; }
          state.notice = "Sorry, I didn't catch that. Please say it again.";
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
        if (!voice) {
          state.error = health.stt ? "This browser can't record audio. Please type." : "Voice is off on the server. Please type.";
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
    paint();

    // Arrived from the mic on the payment screen: the first turn is already recorded; keep talking.
    const handoff = PendingVoice.take(txnId);
    if (handoff && handoff.error) { state.error = handoff.error; paint(); }
    else if (handoff) converse({ audio: handoff });
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

  window.addEventListener("hashchange", route);
  route();
})();
