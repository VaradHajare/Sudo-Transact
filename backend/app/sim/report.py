"""Render the evaluation report (docs/EVALUATION.md) from the JSON produced by the runner."""
from app.domain import CaseClass

SHORT = {c.value: c.value.split("_")[0] for c in CaseClass}
SHORT["AMBIGUOUS"] = "AMB"

HEADLINE = [
    ("False-retry rate (retry offered on a debited / pending / unknown payment)", "false_retry_rate", "pct",
     "safety-critical, target 0"),
    ("False retries (count)", "false_retries", "int", ""),
    ("False-action rate (wrong close / dispute)", "false_action_rate", "pct", "safety-critical"),
    ("Action accuracy", "action_accuracy", "pct", "action in the scenario's acceptable set"),
    ("Diagnosis accuracy", "diagnosis_accuracy", "pct", "class F1–F10 vs ground truth"),
    ("Escalation rate", "escalation_rate", "pct", "human workload"),
    ("Escalation precision", "escalation_precision", "pct", "escalating was an acceptable answer"),
    ("Needless escalations", "needless_escalations", "int", ""),
    ("Actions cancelled by the live re-check", "recheck_cancelled", "int", "world changed before acting"),
    ("…of which the original action was wrong", "recheck_prevented_wrong_action", "int", ""),
    ("SLA breaches caught (dispute + compensation)", "sla_breaches_caught", "of:sla_breaches", ""),
    ("Bank-outage cases answered without a human", "outage_answered_without_human", "of:outage_cases", ""),
    ("Cases classified by the LLM", "llm_classified", "int", "only AMBIGUOUS cases"),
]


def _fmt(m: dict | None, key: str, kind: str) -> str:
    if m is None:
        return "not run"
    v = m.get(key)
    if v is None:
        return "–"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind.startswith("of:"):
        return f"{v} / {m.get(kind[3:])}"
    return str(v)


def render_markdown(r: dict) -> str:
    b = r["baselines"]
    full = b.get("B2") or b["B1"]
    full_name = "B2" if b.get("B2") else "B1"
    cfg = r["config"]
    L = []
    L += ["# Evaluation (simulator)",
          "",
          f"_Generated {r['generated_at']} by `backend/scripts/run_sim.py` (seed {cfg['seed']}, "
          f"{cfg['n_cases']} cases, {r['seconds']} s). Raw numbers: `docs/evaluation.json`._",
          "",
          "> **These are simulator numbers, not real-world accuracy.** The class mix and noise rates are "
          "assumptions for testing (spec 12.3). The answer key comes from the generator's scenario, not "
          "from the engine.",
          "",
          "Baselines (spec 13.1):",
          "- **B0**: rules on the Paytm transaction record only.",
          "- **B1**: B0 + NPCI status + bank ledger + merchant credit, with the live re-check before actions.",
          "- **B2**: B1 + the LLM classifier for cases the rules call AMBIGUOUS (the full system)."
          + ("" if b.get("B2") else " **Not run** (no LLM configured)."),
          "",
          "## Headline",
          "",
          "| Metric | B0 | B1 | B2 | Note |",
          "|---|---:|---:|---:|---|"]
    for label, key, kind, note in HEADLINE:
        L.append(f"| {label} | {_fmt(b['B0'], key, kind)} | {_fmt(b['B1'], key, kind)} | "
                 f"{_fmt(b.get('B2'), key, kind)} | {note} |")

    L += ["", "## Per class", "", f"Diagnosis / action accuracy for each ground-truth class.", "",
          "| Class | Cases | B0 diag | B0 action | B1 diag | B1 action | B2 diag | B2 action |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cls in full["action_accuracy_per_class"]:
        n = sum(full["confusion"].get(cls, {}).values())
        cells = []
        for bl in ("B0", "B1", "B2"):
            m = b.get(bl)
            if m is None:
                cells += ["–", "–"]
                continue
            d, a = m["diagnosis_accuracy_per_class"].get(cls), m["action_accuracy_per_class"].get(cls)
            cells += [f"{d * 100:.0f}%" if d is not None else "–", f"{a * 100:.0f}%" if a is not None else "–"]
        L.append(f"| {cls} | {n} | " + " | ".join(cells) + " |")

    cols = list(SHORT)
    L += ["", f"## Confusion matrix ({full_name})", "",
          "Rows: ground truth. Columns: the class the decision used (AMB = unclassified or LLM confidence "
          "below the threshold, which escalates or waits).", "",
          "| truth \\ predicted | " + " | ".join(SHORT[c] for c in cols) + " |",
          "|---|" + "---:|" * len(cols)]
    for truth, row in full["confusion"].items():
        L.append(f"| {SHORT.get(truth, truth)} | " + " | ".join(str(row.get(c, "")) for c in cols) + " |")

    L += ["", "## Failures (reported, not hidden)", ""]
    for bl in ("B1", "B2"):
        m = b.get(bl)
        if not m:
            continue
        wrong = m["wrong_actions_by_variant"]
        L.append(f"**{bl}:** " + ("no wrong actions." if not wrong else ""))
        for variant, actions in sorted(wrong.items(), key=lambda kv: -sum(kv[1].values())):
            L.append(f"- `{variant}`: " + ", ".join(f"{a} × {n}" for a, n in actions.items()))
        L.append("")
    L += ["Known B1/B2 failure: a payment that really succeeded (NPCI SUCCESS/DEEMED, debited, merchant "
          "credited) while Paytm's own record still says FAILED is flagged as a record-vs-NPCI conflict "
          "and escalated. That is safe (no money moves) but a human handles a case the agent could have "
          "closed. Changing it is a rule decision for the team.", ""]

    if r.get("llm"):
        llm = r["llm"]
        L += ["## LLM classifier (B2)", "",
              f"Model `{llm['model']}`. {llm['distinct_inputs']} distinct evidence patterns reached the classifier "
              f"({llm['calls']} calls, {llm['errors']} failed, median {llm['latency_ms_median']} ms). It sees "
              "structured evidence only. Its answer still goes through the decision rules and the retry gate, and "
              f"confidence below {r['rules']['LLM_MIN_CONFIDENCE']} is treated as AMBIGUOUS.", "",
              "| NPCI | Ledger | Record | LLM class | Confidence |", "|---|---|---|---|---:|"]
        for a in llm["answers"]:
            i = a["input"]
            n = i["npci"]
            npci = "unavailable" if not n.get("available") else f"{n.get('status')}{' final' if n.get('final') else ''}"
            led = "unavailable" if not i["bank_ledger"].get("available") else str(i["bank_ledger"].get("state"))
            rec = f"{i['paytm_record']['status']}{', debited' if i['paytm_record']['debited'] else ''}"
            conf = f"{a['confidence']:.2f}" if a["confidence"] is not None else "–"
            L.append(f"| {npci} | {led} | {rec} | {a['class'] or 'failed'} | {conf} |")
        L.append("")

    if r.get("pipeline_agreement"):
        a = r["pipeline_agreement"]
        L += ["## Simulator vs the real pipeline", "",
              f"{a['sample']} cases were also run through `pipeline.process_transaction` on a throwaway SQLite "
              "database (the code the app runs), with the external world switching between the decision and the "
              f"live re-check. **{a['agree']} / {a['sample']}** gave the same action as the simulator's B1.", "",
              "Time to a prepared answer (server side, per case):", "",
              f"- tap on a case prepared in the background: median {a['open_prepared_ms_median']} ms, "
              f"p95 {a['open_prepared_ms_p95']} ms",
              f"- assembled on demand: median {a['open_on_demand_ms_median']} ms, p95 {a['open_on_demand_ms_p95']} ms",
              "", "Mock sources answer instantly. Real NPCI and bank calls would add network time, which is why "
              "cases are prepared in the background.", ""]
    if r.get("right_payment"):
        a = r["right_payment"]
        L += ["## Right payment attached (spec 1.0 sequence)", "",
              f"For {a['users']} simulated users over the HTTP API: chat about an older failed payment, then a new "
              "payment fails, the user taps the mic on it and says \"issue regarding last payment\".", "",
              f"- session bound to the new payment: **{a['session_bound_to_new_payment']} / {a['users']}**",
              f"- first reply about the new payment (amount matches): **{a['reply_about_new_payment']} / {a['users']}**",
              f"- answered in the first turn: {a['answered_in_first_turn']} / {a['users']}",
              f"- open + first reply, median {a['open_plus_first_reply_ms_median']} ms (templates, no LLM, no voice)",
              "", "In a single-thread support chat, every one of these lands in the old conversation (what we saw in "
              "Paytm's chat, spec 1.0). That is by construction, not measured.", ""]

    L += ["## Scenario mix", "", "| Variant | Cases |", "|---|---:|"]
    L += [f"| `{k}` | {v} |" for k, v in r["variants"].items()]
    L += ["", "Noise: " + ", ".join(f"`{k}` = {cfg[k]}" for k in
                                     ("p_record_stale", "p_state_change", "p_source_outage", "p_settling")), ""]
    return "\n".join(L)
