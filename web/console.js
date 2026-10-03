/*
 * console.js: the ops console (console.html). No framework, no build step.
 *
 * Three tabs:
 *   Live      the app in a phone frame next to the agent activity panel (spec 6.8, demo script 17)
 *   Review    escalated cases with their case files; approve / reject / request info
 *   Numbers   the simulator's B0 / B1 / B2 evaluation (docs/evaluation.json)
 *
 * Components are render functions that take a props object and return an HTML string. All dynamic
 * text goes through esc(). The console only shows what the backend recorded; it decides nothing.
 */
(function () {
  "use strict";

  const $root = document.getElementById("console");
  document.title = `${BRAND.appName} ops console`;
  const POLL_MS = 1500;

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  const timeOnly = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }) : "");
  const pct = (v) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(1)}%`);
  const shortClass = (c) => (c ? String(c).split("_")[0] : "–");

  const state = {
    tab: (location.hash.replace("#", "") || "live"),
    follow: true,
    liveCaseId: null,
    liveKey: "",
    seenEventIds: new Set(),
    queue: [],
    reviewId: null,
    report: undefined,
    note: "",
  };

  // ------------------------------------------------------------------ event formatting
  /** Which of the agent's jobs (spec 6.9) an event belongs to. */
  const JOB = {
    CASE_CREATED: "Prepare", EVIDENCE_ASSEMBLED: "Prepare", DIAGNOSED: "Prepare",
    DECIDED: "Rules", RECHECK_PASSED: "Rules", RECHECK_CHANGED: "Rules", RETRY_GATE_EVALUATED: "Rules",
    LLM_CLASSIFIED: "LLM", LLM_INTENT: "LLM", LLM_REPHRASE: "LLM", LLM_CASE_SUMMARY: "LLM", NUMBER_CHECK_FAILED: "LLM",
    CASE_OPENED_BY_USER: "Brief", USER_TURN: "Converse", STT: "Converse", AGENT_REPLIED: "Converse",
    JOB_RUN: "Follow through", DISPUTE_RAISED: "Follow through", COMPENSATION_FLAGGED: "Follow through",
    COMPENSATION_UPDATED: "Follow through", NOTIFIED: "Follow through",
    ESCALATED: "Hand off", REVIEW_DECIDED: "Hand off",
  };

  function sourceTags(p) {
    const n = p.npci || {}, l = p.ledger || {}, m = p.merchant || {};
    const npci = n.available === false ? "unavailable" : `${n.status}${n.final ? " (final)" : ""}${n.reason_code ? " · " + n.reason_code : ""}`;
    const ledger = l.available === false ? "unavailable" : `${l.state}${l.debit_count > 1 ? " ×" + l.debit_count : ""}`;
    const merchant = m.available === false ? "unavailable" : m.credited ? "credited" : "not credited";
    const tag = (label, value, bad) => `<span class="tag ${bad ? "tag--bad" : ""}">${esc(label)}: ${esc(value)}</span>`;
    const issues = [...(p.conflicts || []), ...(p.suspicious || [])].map((c) => `<span class="tag tag--bad">${esc(c)}</span>`).join("");
    const settling = (p.settling || []).map((c) => `<span class="tag tag--warn">settling: ${esc(c)}</span>`).join("");
    return tag("NPCI", npci, n.available === false) + tag("Ledger", ledger, l.available === false) + tag("Merchant", merchant, false) + issues + settling;
  }

  /** Turn one audit event into { title, detail } (HTML). */
  function describe(e) {
    const p = e.payload || {};
    switch (e.event) {
      case "CASE_CREATED": return { title: "Case created", detail: `trigger ${esc(p.trigger)}` };
      case "EVIDENCE_ASSEMBLED": return { title: "Evidence fetched from every source", detail: sourceTags(p) };
      case "DIAGNOSED": return {
        title: `Diagnosed <span class="tag tag--info">${esc(p.case_class)}</span>`,
        detail: `${esc(p.source)} · confidence ${Number(p.confidence ?? 0).toFixed(2)}${p.reasons && p.reasons.length ? " · " + esc(p.reasons.join("; ")) : ""}`,
      };
      case "LLM_CLASSIFIED": return {
        title: `LLM classified the ambiguous case${p.result ? ` <span class="tag tag--info">${esc(p.result.case_class)}</span>` : ""}`,
        detail: p.result ? `confidence ${Number(p.result.confidence).toFixed(2)} · ${esc(p.latency_ms)} ms · still goes through the rules` : `failed (${esc(p.error)}): rules fallback`,
      };
      case "DECIDED": return {
        title: `Rule ${esc(p.rule)} → <span class="tag ${p.action === "ESCALATE" ? "tag--bad" : p.action === "OFFER_RETRY" || p.action === "CLOSE" ? "tag--good" : "tag--info"}">${esc(p.action)}</span>`,
        detail: (p.deadline ? `deadline ${esc(new Date(p.deadline).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }))}` : "") +
          (p.trace && p.trace.length ? `<ul class="trace">${p.trace.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""),
      };
      case "RECHECK_PASSED": return { title: `Live re-check passed <span class="tag tag--good">safe to act</span>`, detail: `before ${esc(p.before_action)}` };
      case "RECHECK_CHANGED": return {
        title: `Live re-check: the world changed <span class="tag tag--warn">action cancelled</span>`,
        detail: `before ${esc(p.before_action)}${p.changed_sources ? " · changed: " + esc(p.changed_sources.join(", ")) : ""} · re-assembling (rule 0)`,
      };
      case "RETRY_OFFERED": return { title: "Safe retry offered", detail: "the user still has to confirm and enter their PIN" };
      case "RETRY_CONFIRM_REQUESTED": return { title: "User said yes to the retry", detail: "" };
      case "RETRY_GATE_EVALUATED": {
        const checks = p.checks || [];
        const passed = checks.filter((c) => c.passed === true).length;
        return {
          title: `Retry gate: ${passed}/${checks.length} checks ${p.passes ? '<span class="tag tag--good">pass</span>' : '<span class="tag tag--bad">fail</span>'}`,
          detail: checks.filter((c) => c.passed !== true).map((c) => `<span class="tag tag--bad">${esc(c.code)}</span>`).join(""),
        };
      }
      case "RETRY_CONFIRMED": return { title: "Pay screen opened (pre-filled from the Paytm record)", detail: `${esc(p.payee_name)} · ${esc(formatPaise(p.amount_paise || 0))}` };
      case "RETRY_PAYMENT_MADE": return { title: "User paid again with their PIN", detail: esc(p.new_txn_id) };
      case "RESOLVED_BY_RETRY": return { title: "Resolved by the retry", detail: "" };
      case "RETRY_DECLINED": return { title: "User declined the retry", detail: "" };
      case "DISPUTE_RAISED": return { title: `Dispute raised with NPCI UDIR <span class="tag tag--warn">${esc(p.udir_ref)}</span>`, detail: `${esc(p.kind)} · ${esc(formatPaise(p.amount_paise || 0))}` };
      case "COMPENSATION_FLAGGED": return { title: `Compensation flagged: ${esc(formatPaise(p.amount_paise || 0))}`, detail: `${esc(p.days_late)} day(s) late × ${esc(formatPaise(p.per_day_paise || 0))}/day` };
      case "COMPENSATION_UPDATED": return { title: `Compensation now ${esc(formatPaise(p.amount_paise || 0))}`, detail: `${esc(p.days_late)} day(s) late` };
      case "ESCALATED": return { title: `Escalated to a human <span class="tag tag--bad">case file written</span>`, detail: esc(p.reason) };
      case "NOTIFIED": return { title: "New message in the payment's chat + history badge", detail: esc(p.situation) };
      case "CASE_OPENED_BY_USER": return { title: "User tapped the mic on this payment", detail: p.prepared ? "case was already prepared in the background" : "assembled on demand" };
      case "USER_TURN": return { title: `User spoke (${esc(p.input)}, ${esc(p.lang)})`, detail: `intent ${esc(p.intent)}${p.chip ? " · chip " + esc(p.chip) : ""}` };
      case "STT": return { title: "Speech to text (Sarvam)", detail: p.rejected ? "no speech" : `${esc(p.latency_ms)} ms · ${esc(p.language_code)}` };
      case "LLM_INTENT": return { title: "LLM read the intent", detail: `${esc(p.intent || "")} ${p.ok === false ? "(failed: keyword fallback)" : ""}` };
      case "LLM_REPHRASE": return { title: "LLM rephrase", detail: p.ok ? `${esc(p.latency_ms)} ms · ${esc(p.reason || "")}` : "kept the template" };
      case "NUMBER_CHECK_FAILED": return { title: '<span class="tag tag--bad">Number check failed</span> template used instead', detail: esc((p.numbers || []).join(", ")) };
      case "AGENT_REPLIED": return { title: `Agent replied (${esc(p.lang)})`, detail: `${esc(p.situation)} · rule ${esc(p.rule)} · ${esc(p.decision)}` };
      case "JOB_RUN": return { title: `Background job: ${esc(p.kind)}`, detail: `${esc(p.from)} → ${esc(p.to)}${p.rule ? " · rule " + esc(p.rule) : ""}` };
      case "LLM_CASE_SUMMARY": return { title: "LLM wrote the reviewer summary", detail: p.ok ? `${esc(p.latency_ms)} ms` : `failed: ${esc(p.error)}` };
      case "REVIEW_DECIDED": return { title: `Reviewer: <span class="tag tag--info">${esc(p.decision)}</span>`, detail: esc(p.reviewer) };
      case "CLAIMS_RECORDED": return { title: "User claims recorded (untrusted, compared with evidence)", detail: (p.claims || []).map((c) => `<span class="tag">${esc(c.kind)}: ${esc(c.value)}</span>`).join("") };
      default: return { title: esc(e.event), detail: "" };
    }
  }

  // ------------------------------------------------------------------ components

  /** ConsoleBar. props: { tab, queueCount } */
  function ConsoleBar({ tab, queueCount }) {
    const t = (id, label, extra) => `<button class="console__tab" data-tab="${id}" aria-selected="${tab === id}">${label}${extra || ""}</button>`;
    return `
      <header class="console__bar">
        <div>
          <p class="console__title">${esc(BRAND.appName)} ${esc(BRAND.assistantName)} · ops console</p>
          <div class="console__sub">${esc(BRAND.prototypeLabel)}</div>
        </div>
        <nav class="console__tabs" role="tablist">
          ${t("live", "Live")}
          ${t("review", "Review queue", queueCount ? `<span class="console__count">${queueCount}</span>` : "")}
          ${t("numbers", "Numbers")}
        </nav>
      </header>`;
  }

  /** EventItem. props: { event, isNew } */
  function EventItem({ event, isNew }) {
    const d = describe(event);
    const job = JOB[event.event];
    return `
      <li class="event ${isNew ? "event--new" : ""}">
        <span class="event__time">${esc(timeOnly(event.ts))}</span>
        <span class="event__actor event__actor--${esc(event.actor)}">${esc(event.actor)}</span>
        <div>
          <div class="event__title">${d.title}${job ? ` <span class="tag">${esc(job)}</span>` : ""}</div>
          ${d.detail ? `<div class="event__detail">${d.detail}</div>` : ""}
        </div>
      </li>`;
  }

  /** CaseHeader. props: { caseView } (case from /v1/review/cases/{id}) */
  function CaseHeader({ caseView: c }) {
    return `
      <div class="case-summary">
        <span class="case-summary__payee">${esc(c.card.payeeName)}</span>
        <span>${esc(formatPaise(c.card.amountPaise))}</span>
        <span class="tag">${esc(c.card.status)}</span>
        ${c.class ? `<span class="tag tag--info">${esc(c.class)}</span>` : ""}
        ${c.decision ? `<span class="tag">rule ${esc(c.rule)} → ${esc(c.decision)}</span>` : ""}
        <span class="tag ${c.state === "ESCALATED" ? "tag--bad" : ""}">${esc(c.state)}</span>
        ${c.status_line ? `<span class="muted">${esc(c.status_line)}</span>` : ""}
      </div>`;
  }

  /** ActivityPanel. props: { cases, detail, follow } */
  function ActivityPanel({ cases, detail, follow }) {
    const options = cases.map((c) => `<option value="${esc(c.id)}" ${detail && detail.case.id === c.id ? "selected" : ""}>${esc(c.payee)} · ${esc(formatPaise(c.amount_paise))} · ${esc(shortClass(c.class))} · ${esc(c.state)}</option>`).join("");
    const events = detail ? detail.events : [];
    return `
      <section class="panel" aria-label="Agent activity">
        <div class="panel__head">
          <h2 class="panel__title">Agent activity</h2>
          <span class="panel__spacer"></span>
          <label class="toggle"><input type="checkbox" data-follow ${follow ? "checked" : ""}> follow the latest case</label>
          <select class="select" data-case-select aria-label="Case">${options}</select>
        </div>
        ${detail ? CaseHeader({ caseView: detail.case }) : '<div class="state">No cases yet.</div>'}
        <ol class="timeline" data-timeline>
          ${events.map((e) => EventItem({ event: e, isNew: state.seenEventIds.size > 0 && !state.seenEventIds.has(e.id) })).join("")}
        </ol>
      </section>`;
  }

  /** LiveView: the phone frame and demo tools; the activity panel mounts into [data-live-panel].
   *  props: { note } */
  function LiveView(props) {
    return `
      <div class="live">
        <div>
          <iframe class="live__phone" src="./#/" title="The app, as the user sees it" allow="microphone; autoplay"></iframe>
          <div class="live__tools">
            <button class="tool-btn" data-demo="skip">Skip time +1 day</button>
            <button class="tool-btn" data-demo="outage">Bank outage: fail a payment</button>
            <button class="tool-btn" data-demo="late-debit">Late debit on Sharma Medicals</button>
            <button class="tool-btn" data-demo="phone-home">Phone: home</button>
          </div>
          <div class="tool-note" data-tool-note>${esc(props.note)}</div>
        </div>
        <div data-live-panel></div>
      </div>`;
  }

  /** SourceBox. props: { name, value, bad } */
  function SourceBox({ name, value, bad }) {
    return `<div class="cf-source"><div class="cf-source__name">${esc(name)}</div><div class="cf-source__value ${bad ? "is-bad" : ""}">${esc(value)}</div></div>`;
  }

  /** CaseFile: everything a reviewer needs. props: { item } (queue entry or review detail) */
  function CaseFile({ item }) {
    const cf = item.case_file || {};
    const ev = cf.evidence || {};
    const rec = ev.paytm_record || {}, n = ev.npci || {}, l = ev.bank_ledger || {}, m = ev.merchant || {};
    const issues = [...(cf.conflicts || []), ...(cf.suspicious || [])];
    return `
      ${cf.llm_summary ? `<div class="cf-h">Summary (LLM, numbers checked against the case file)</div><p class="cf-quote">${esc(cf.llm_summary)}</p>` : ""}
      <div class="cf-h">What happened</div>
      <p class="cf-quote">${esc(cf.summary || item.escalation_reason || "")}</p>
      <div class="cf-h">Evidence from each source</div>
      <div class="cf-grid">
        ${SourceBox({ name: "Paytm record", value: `${rec.status || "–"}${rec.debited ? ", debited" : ""}${rec.failure_code ? " · " + rec.failure_code : ""}` })}
        ${SourceBox({ name: "NPCI", value: n.available === false ? "unavailable" : `${n.status || "–"}${n.final ? " (final)" : ""}`, bad: n.available === false })}
        ${SourceBox({ name: "Bank ledger", value: l.available === false ? "unavailable" : `${l.state || "–"}${l.debit_count > 1 ? " ×" + l.debit_count : ""}${l.amount_paise ? " · " + formatPaise(l.amount_paise) : ""}`, bad: l.available === false })}
        ${SourceBox({ name: "Merchant", value: m.available === false ? "unavailable" : m.credited ? "credited" : "not credited" })}
      </div>
      ${issues.length ? `<div class="cf-h">Conflicts and suspicious signals</div><ul class="cf-list">${issues.map((c) => `<li><span class="tag tag--bad">${esc(c.code)}</span> ${esc(c.detail)}</li>`).join("")}</ul>` : ""}
      ${(cf.claims || []).length ? `<div class="cf-h">What the user claimed (untrusted)</div><ul class="cf-list">${cf.claims.map((c) => `<li>${esc(c.kind)}: ${esc(c.value)}</li>`).join("")}</ul>` : ""}
      ${cf.diagnosis ? `<div class="cf-h">Diagnosis</div><p class="muted">${esc(cf.diagnosis.case_class)} · ${esc(cf.diagnosis.source)} · confidence ${Number(cf.diagnosis.confidence).toFixed(2)}</p>` : ""}
      ${(cf.rule_trace || []).length ? `<div class="cf-h">Rule trace</div><ul class="trace">${cf.rule_trace.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      <div class="cf-h">Recommended actions</div>
      <ul class="cf-list">${(cf.recommended_actions || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      ${cf.agent_answer ? `<div class="cf-h">What the agent told the user</div><p class="cf-quote">${esc(cf.agent_answer)}</p>` : ""}`;
  }

  /** ReviewView. props: { queue, selectedId } */
  function ReviewView({ queue, selectedId }) {
    const sel = queue.find((c) => c.id === selectedId) || queue[0];
    const list = queue.length
      ? `<ul class="queue">${queue.map((c) => `
          <li><button class="queue__item" data-review="${esc(c.id)}" aria-current="${sel && sel.id === c.id}">
            <div class="queue__name">${esc(c.card.payeeName)} · ${esc(formatPaise(c.card.amountPaise))}</div>
            <div class="queue__meta">${esc(shortClass(c.class))} · ${esc(c.escalation_reason || "")}</div>
          </button></li>`).join("")}</ul>`
      : '<div class="state">No escalated cases. Every case so far was handled without a human.</div>';
    return `
      <div class="review">
        <section class="panel"><div class="panel__head"><h2 class="panel__title">Escalated</h2></div>${list}</section>
        <section class="panel">
          ${sel ? `
            <div class="panel__head"><h2 class="panel__title">Case file</h2><span class="panel__spacer"></span><span class="muted">${esc(sel.id)} · ${esc(sel.txn_id)}</span></div>
            ${CaseHeader({ caseView: sel })}
            ${CaseFile({ item: sel })}
            <div class="cf-h">Your decision</div>
            <form data-decide="${esc(sel.id)}">
              <textarea class="notes" name="notes" placeholder="Notes (internal: the user never sees them)"></textarea>
              <div class="decide">
                <button class="tool-btn tool-btn--ok" name="decision" value="APPROVE">Approve: take it up with the bank</button>
                <button class="tool-btn tool-btn--danger" name="decision" value="REJECT">Reject: no problem confirmed</button>
                <button class="tool-btn" name="decision" value="REQUEST_INFO">Ask the user for more info</button>
              </div>
              <p class="tool-note">The user gets a fixed message in their language in that payment's chat.</p>
            </form>` : '<div class="state">Nothing to review.</div>'}
        </section>
      </div>`;
  }

  /** Kpi. props: { label, value, sub } */
  function Kpi({ label, value, sub }) {
    return `<div class="kpi"><div class="kpi__label">${esc(label)}</div><div class="kpi__value">${esc(value)}</div>${sub ? `<div class="kpi__sub">${esc(sub)}</div>` : ""}</div>`;
  }

  /** NumbersView. props: { report } (docs/evaluation.json, or null) */
  function NumbersView({ report }) {
    if (report === undefined) return '<div class="state"><div class="spinner"></div>Loading…</div>';
    if (report === null) return '<div class="state">No evaluation yet. Run <code>backend/scripts/run_sim.py</code>.</div>';
    const b = report.baselines;
    const full = b.B2 || b.B1;
    const fullName = b.B2 ? "B2" : "B1";
    const cfg = report.config;
    const rows = [
      ["False-retry rate (target 0)", "false_retry_rate", "pct", true],
      ["False retries", "false_retries", "int", true],
      ["Wrong close / dispute rate", "false_action_rate", "pct", true],
      ["Action accuracy", "action_accuracy", "pct"],
      ["Diagnosis accuracy", "diagnosis_accuracy", "pct"],
      ["Escalation rate", "escalation_rate", "pct"],
      ["Actions cancelled by the live re-check", "recheck_cancelled", "int"],
      ["SLA breaches caught", "sla_breaches_caught", "of:sla_breaches"],
      ["Outage cases answered without a human", "outage_answered_without_human", "of:outage_cases"],
      ["Cases classified by the LLM", "llm_classified", "int"],
    ];
    const cell = (m, key, kind, safety) => {
      if (!m) return '<td class="muted">not run</td>';
      const v = m[key];
      const text = kind === "pct" ? pct(v) : kind.startsWith("of:") ? `${v} / ${m[kind.slice(3)]}` : String(v ?? "–");
      const cls = safety ? (v ? "is-bad" : "is-good") : "";
      return `<td class="${cls}">${esc(text)}</td>`;
    };
    const classes = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "AMBIGUOUS"];
    const matrixRows = Object.entries(full.confusion).map(([truth, row]) => {
      const total = Object.values(row).reduce((a, x) => a + x, 0) || 1;
      return `<tr><td>${esc(shortClass(truth))}</td>${classes.map((c) => {
        const key = Object.keys(row).find((k) => shortClass(k) === c || k === c);
        const n = key ? row[key] : 0;
        const diag = shortClass(truth) === c;
        return `<td class="${diag ? "is-diag" : ""}" style="background: rgba(var(--color-heat), ${(n / total * 0.6).toFixed(2)})">${n || ""}</td>`;
      }).join("")}</tr>`;
    }).join("");
    const wrong = (m) => Object.entries(m.wrong_actions_by_variant || {});
    const a = report.pipeline_agreement, rp = report.right_payment;
    return `
      <p class="numbers__note">Simulator numbers, not real-world accuracy. ${esc(cfg.n_cases)} generated cases (seed ${esc(cfg.seed)}); the class mix and noise are assumptions. Generated ${esc(report.generated_at)}.</p>
      <div class="kpis">
        ${Kpi({ label: "False retries (full system)", value: String(full.false_retries), sub: `B0 (record only): ${b.B0.false_retries} · ${pct(b.B0.false_retry_rate)}` })}
        ${Kpi({ label: "Wrong closes / disputes", value: String(full.false_actions), sub: `B0: ${b.B0.false_actions}` })}
        ${Kpi({ label: "Actions cancelled by the re-check", value: String(full.recheck_cancelled), sub: `${full.recheck_prevented_wrong_action} would have been wrong` })}
        ${Kpi({ label: "Right payment attached", value: rp ? pct(rp.right_payment_rate) : "–", sub: rp ? `${rp.users} users, spec 1.0 sequence over HTTP` : "" })}
      </div>
      <section class="panel">
        <div class="panel__head"><h2 class="panel__title">B0 → B1 → B2</h2><span class="muted">B0 record only · B1 + NPCI, ledger, merchant, re-check · B2 + LLM for ambiguous cases</span></div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th>Metric</th><th>B0</th><th>B1</th><th>B2</th></tr></thead>
          <tbody>${rows.map(([label, key, kind, safety]) => `<tr><td>${esc(label)}</td>${cell(b.B0, key, kind, safety)}${cell(b.B1, key, kind, safety)}${cell(b.B2, key, kind, safety)}</tr>`).join("")}</tbody>
        </table></div>
      </section>
      <section class="panel">
        <div class="panel__head"><h2 class="panel__title">Confusion matrix (${fullName})</h2><span class="muted">rows: ground truth · columns: class the decision used</span></div>
        <div class="table-wrap"><table class="table matrix">
          <thead><tr><th>truth \\ predicted</th>${classes.map((c) => `<th>${c === "AMBIGUOUS" ? "AMB" : c}</th>`).join("")}</tr></thead>
          <tbody>${matrixRows}</tbody>
        </table></div>
      </section>
      <section class="panel">
        <div class="panel__head"><h2 class="panel__title">Failures (reported, not hidden)</h2></div>
        ${["B1", "B2"].filter((k) => b[k]).map((k) => `<p><strong>${k}:</strong> ${wrong(b[k]).length ? "" : "no wrong actions"}</p>${wrong(b[k]).length ? `<ul class="cf-list">${wrong(b[k]).map(([v, acts]) => `<li><code>${esc(v)}</code>: ${esc(Object.entries(acts).map(([x, n]) => `${x} × ${n}`).join(", "))}</li>`).join("")}</ul>` : ""}`).join("")}
        ${a ? `<p class="muted">Real pipeline cross-check: ${a.agree}/${a.sample} cases gave the same action through <code>process_transaction</code>. Tap on a prepared case: median ${a.open_prepared_ms_median} ms server-side (mock sources).</p>` : ""}
      </section>`;
  }

  // ------------------------------------------------------------------ data + painting
  let detailCache = null;
  let casesCache = [];

  async function refreshLive(force) {
    const cases = await ReviewRepository.cases();
    casesCache = cases;
    if (state.follow && cases.length) state.liveCaseId = cases[0].id;
    if (!state.liveCaseId && cases.length) state.liveCaseId = cases[0].id;
    const current = cases.find((c) => c.id === state.liveCaseId);
    const key = current ? `${current.id}:${current.last_event_id}` : "";
    if (!force && key === state.liveKey) return false;
    const switched = !detailCache || !current || detailCache.case.id !== current.id;
    detailCache = current ? await ReviewRepository.detail(current.id) : null;
    if (switched) state.seenEventIds = new Set();
    state.liveKey = key;
    return true;
  }

  async function refreshQueue() {
    state.queue = await ReviewRepository.queue();
  }

  function paintBar() {
    const bar = $root.querySelector(".console__bar");
    const html = ConsoleBar({ tab: state.tab, queueCount: state.queue.length });
    if (bar) bar.outerHTML = html; else $root.insertAdjacentHTML("afterbegin", html);
  }

  function paintLivePanel() {
    const host = $root.querySelector("[data-live-panel]");
    if (!host) return;
    host.innerHTML = ActivityPanel({ cases: casesCache, detail: detailCache, follow: state.follow });
    const tl = host.querySelector("[data-timeline]");
    if (tl) tl.scrollTop = tl.scrollHeight;
    if (detailCache) detailCache.events.forEach((e) => state.seenEventIds.add(e.id));
  }

  async function paint() {
    $root.innerHTML = "";
    paintBar();
    const main = document.createElement("main");
    main.className = "console__main";
    $root.appendChild(main);
    if (state.tab === "live") {
      // The phone iframe is painted once; only the activity panel repaints while polling.
      main.innerHTML = LiveView({ note: state.note });
      paintLivePanel();
    } else if (state.tab === "review") {
      main.innerHTML = ReviewView({ queue: state.queue, selectedId: state.reviewId });
    } else {
      main.innerHTML = NumbersView({ report: state.report });
      if (state.report === undefined) {
        state.report = await ReviewRepository.evaluation().catch(() => null);
        if (state.tab === "numbers") main.innerHTML = NumbersView({ report: state.report });
      }
    }
  }

  function setNote(text) {
    state.note = text;
    const el = $root.querySelector("[data-tool-note]");
    if (el) el.textContent = text;
  }

  // ------------------------------------------------------------------ events
  $root.addEventListener("click", async (ev) => {
    const tab = ev.target.closest("[data-tab]");
    if (tab) {
      state.tab = tab.dataset.tab;
      history.replaceState(null, "", "#" + state.tab);
      if (state.tab === "review") await refreshQueue();
      paint();
      return;
    }
    const item = ev.target.closest("[data-review]");
    if (item) {
      state.reviewId = item.dataset.review;
      paint();
      return;
    }
    const demo = ev.target.closest("[data-demo]");
    if (demo) {
      demo.disabled = true;
      try {
        await runDemo(demo.dataset.demo);
      } catch (e) {
        setNote(`Failed: ${e.message}`);
      } finally {
        demo.disabled = false;
      }
    }
  });

  $root.addEventListener("change", async (ev) => {
    if (ev.target.matches("[data-follow]")) {
      state.follow = ev.target.checked;
      if (state.follow) { await refreshLive(true); paintLivePanel(); }
    } else if (ev.target.matches("[data-case-select]")) {
      state.follow = false;
      state.liveCaseId = ev.target.value;
      await refreshLive(true);
      paintLivePanel();
    }
  });

  $root.addEventListener("submit", async (ev) => {
    const form = ev.target.closest("[data-decide]");
    if (!form) return;
    ev.preventDefault();
    const decision = ev.submitter && ev.submitter.value;
    if (!decision) return;
    form.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      await ReviewRepository.decide(form.dataset.decide, decision, form.elements.notes.value);
      await refreshQueue();
      state.reviewId = null;
      paint();
    } catch (e) {
      form.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      form.querySelector(".tool-note").textContent = `Failed: ${e.message}`;
    }
  });

  async function runDemo(kind) {
    const phone = $root.querySelector(".live__phone");
    if (kind === "phone-home") {
      phone.src = "./#/";
      return;
    }
    if (kind === "skip") {
      const r = await DemoRepository.skipDays(1);
      setNote(`Clock moved +1 day. ${r.jobs_run ? r.jobs_run.length : 0} background job(s) ran.`);
    } else if (kind === "outage") {
      const r = await DemoRepository.scenario("bank_outage");
      setNote(r.message);
      phone.src = `./#/txn/${encodeURIComponent(r.txn_id)}`;
    } else if (kind === "late-debit") {
      const r = await DemoRepository.scenario("late_debit");
      setNote(r.message);
    }
    await refreshLive(true);
    paintLivePanel();
  }

  // ------------------------------------------------------------------ start
  async function poll() {
    try {
      if (state.tab === "live" && (await refreshLive(false))) paintLivePanel();
      const before = state.queue.length;
      await refreshQueue();
      if (state.queue.length !== before) paintBar();
    } catch (e) {
      /* server restarting: try again next tick */
    }
    setTimeout(poll, POLL_MS);
  }

  (async function start() {
    $root.innerHTML = '<div class="state"><div class="spinner"></div>Loading…</div>';
    try {
      await Promise.all([refreshLive(true), refreshQueue()]);
    } catch (e) {
      $root.innerHTML = `<div class="state state--error">Could not reach the backend: ${esc(e.message)}</div>`;
      return;
    }
    await paint();
    setTimeout(poll, POLL_MS);
  })();
})();
