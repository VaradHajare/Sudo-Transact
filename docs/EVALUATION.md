# Evaluation (simulator)

_Generated 2026-10-03T09:38:16Z by `backend/scripts/run_sim.py` (seed 7, 3000 cases, 174.4 s). Raw numbers: `docs/evaluation.json`._

> **These are simulator numbers, not real-world accuracy.** The class mix and noise rates are assumptions for testing (spec 12.3). The answer key comes from the generator's scenario, not from the engine.

Baselines (spec 13.1):
- **B0**: rules on the Paytm transaction record only.
- **B1**: B0 + NPCI status + bank ledger + merchant credit, with the live re-check before actions.
- **B2**: B1 + the LLM classifier for cases the rules call AMBIGUOUS (the full system).

## Headline

| Metric | B0 | B1 | B2 | Note |
|---|---:|---:|---:|---|
| False-retry rate (retry offered on a debited / pending / unknown payment) | 27.8% | 0.0% | 0.0% | safety-critical, target 0 |
| False retries (count) | 670 | 0 | 0 |  |
| False-action rate (wrong close / dispute) | 65.5% | 0.0% | 0.0% | safety-critical |
| Action accuracy | 59.5% | 98.2% | 98.2% | action in the scenario's acceptable set |
| Diagnosis accuracy | 60.5% | 93.1% | 96.5% | class F1–F10 vs ground truth |
| Escalation rate | 7.9% | 21.9% | 20.9% | human workload |
| Escalation precision | 100.0% | 91.9% | 91.5% | escalating was an acceptable answer |
| Needless escalations | 0 | 53 | 53 |  |
| Actions cancelled by the live re-check | 0 | 95 | 95 | world changed before acting |
| …of which the original action was wrong | 0 | 95 | 95 |  |
| SLA breaches caught (dispute + compensation) | 108 / 156 | 156 / 156 | 156 / 156 |  |
| Bank-outage cases answered without a human | 305 / 305 | 289 / 305 | 305 / 305 |  |
| Cases classified by the LLM | 0 | 0 | 130 | only AMBIGUOUS cases |

## Per class

Diagnosis / action accuracy for each ground-truth class.

| Class | Cases | B0 diag | B0 action | B1 diag | B1 action | B2 diag | B2 action |
|---|---:|---:|---:|---:|---:|---:|---:|
| F10_SUSPICIOUS | 238 | 100% | 100% | 100% | 100% | 100% | 100% |
| F1_DECLINED_PRE_DEBIT | 393 | 100% | 93% | 92% | 100% | 100% | 100% |
| F2_TIMEOUT_PRE_DEBIT | 334 | 100% | 69% | 94% | 100% | 98% | 100% |
| F3_PENDING | 306 | 47% | 79% | 96% | 100% | 98% | 100% |
| F4_DEBIT_NO_CREDIT | 503 | 61% | 60% | 94% | 100% | 96% | 100% |
| F5_DEEMED_SUCCESS | 210 | 45% | 46% | 70% | 75% | 72% | 75% |
| F6_BANK_DOWNTIME | 305 | 100% | 100% | 95% | 100% | 100% | 100% |
| F7_DUPLICATE_DEBIT | 185 | 0% | 0% | 91% | 100% | 97% | 100% |
| F8_ALREADY_REVERSED | 315 | 0% | 1% | 94% | 100% | 97% | 100% |
| F9_CONFLICT | 211 | 0% | 0% | 100% | 100% | 100% | 100% |

## Confusion matrix (B2)

Rows: ground truth. Columns: the class the decision used (AMB = unclassified or LLM confidence below the threshold, which escalates or waits).

| truth \ predicted | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | AMB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F10 |  |  |  |  |  |  |  |  |  | 238 |  |
| F1 | 393 |  |  |  |  |  |  |  |  |  |  |
| F2 | 3 | 326 |  |  |  |  |  |  |  |  | 5 |
| F3 | 4 |  | 301 |  |  |  |  |  | 1 |  |  |
| F4 | 5 |  |  | 483 |  |  |  |  | 2 |  | 13 |
| F5 |  |  |  |  | 152 |  |  |  | 56 |  | 2 |
| F6 |  |  |  |  |  | 305 |  |  |  |  |  |
| F7 |  |  |  |  | 5 |  | 180 |  |  |  |  |
| F8 |  |  |  | 4 |  |  |  | 307 |  |  | 4 |
| F9 |  |  |  |  |  |  |  |  | 211 |  |  |

## Failures (reported, not hidden)

**B1:** 
- `f5_deemed_success_stale_record`: ESCALATE (rule 1) × 53

**B2:** 
- `f5_deemed_success_stale_record`: ESCALATE (rule 1) × 53

Known B1/B2 failure: a payment that really succeeded (NPCI SUCCESS/DEEMED, debited, merchant credited) while Paytm's own record still says FAILED is flagged as a record-vs-NPCI conflict and escalated. That is safe (no money moves) but a human handles a case the agent could have closed. Changing it is a rule decision for the team.

## LLM classifier (B2)

Model `deepseek-flash`. 45 distinct evidence patterns reached the classifier (45 calls, 8 failed, median 1819 ms). It sees structured evidence only. Its answer still goes through the decision rules and the retry gate, and confidence below 0.7 is treated as AMBIGUOUS.

| NPCI | Ledger | Record | LLM class | Confidence |
|---|---|---|---|---:|
| DEEMED final | unavailable | SUCCESS, debited | F5_DEEMED_SUCCESS | 0.90 |
| unavailable | NO_DEBIT | FAILED | F6_BANK_DOWNTIME | 0.85 |
| FAILED final | unavailable | FAILED | failed | – |
| FAILED final | unavailable | FAILED | F1_DECLINED_PRE_DEBIT | 0.90 |
| FAILED final | unavailable | FAILED | F6_BANK_DOWNTIME | 0.90 |
| unavailable | NO_DEBIT | FAILED | F1_DECLINED_PRE_DEBIT | 0.80 |
| PENDING | unavailable | PENDING | F3_PENDING | 0.78 |
| unavailable | DEBITED | SUCCESS, debited | F7_DUPLICATE_DEBIT | 0.90 |
| unavailable | NO_DEBIT | FAILED | F1_DECLINED_PRE_DEBIT | 0.95 |
| FAILED final | unavailable | FAILED, debited | F4_DEBIT_NO_CREDIT | 0.92 |
| unavailable | NO_DEBIT | FAILED | F1_DECLINED_PRE_DEBIT | 0.72 |
| SUCCESS final | unavailable | SUCCESS, debited | F5_DEEMED_SUCCESS | 0.95 |
| unavailable | DEBITED | FAILED | F9_CONFLICT | 0.65 |
| unavailable | NO_DEBIT | FAILED | F1_DECLINED_PRE_DEBIT | 0.95 |
| FAILED | unavailable | FAILED | failed | – |
| unavailable | NO_DEBIT | FAILED | F6_BANK_DOWNTIME | 0.82 |
| unavailable | REVERSED | FAILED, debited | F8_ALREADY_REVERSED | 0.90 |
| FAILED | unavailable | FAILED | F2_TIMEOUT_PRE_DEBIT | 0.84 |
| FAILED final | unavailable | FAILED | F6_BANK_DOWNTIME | 0.90 |
| FAILED final | unavailable | FAILED | F1_DECLINED_PRE_DEBIT | 0.92 |
| unavailable | DEBITED | FAILED, debited | F4_DEBIT_NO_CREDIT | 0.90 |
| PENDING | unavailable | FAILED | F9_CONFLICT | 0.70 |
| FAILED final | unavailable | FAILED | F2_TIMEOUT_PRE_DEBIT | 0.90 |
| unavailable | DEBITED | FAILED, debited | F4_DEBIT_NO_CREDIT | 0.92 |
| unavailable | NO_DEBIT | FAILED | F6_BANK_DOWNTIME | 0.82 |
| unavailable | DEBITED | PENDING | F5_DEEMED_SUCCESS | 0.82 |
| unavailable | NO_DEBIT | FAILED | F2_TIMEOUT_PRE_DEBIT | 0.92 |
| unavailable | NO_DEBIT | PENDING | F3_PENDING | 0.70 |
| FAILED final | unavailable | FAILED | F1_DECLINED_PRE_DEBIT | 0.95 |
| FAILED final | unavailable | FAILED | F2_TIMEOUT_PRE_DEBIT | 0.86 |
| FAILED final | unavailable | FAILED | F1_DECLINED_PRE_DEBIT | 0.95 |
| FAILED final | unavailable | FAILED | failed | – |
| unavailable | REVERSED | FAILED | failed | – |
| FAILED final | unavailable | FAILED | F6_BANK_DOWNTIME | 0.95 |
| PENDING | unavailable | FAILED, debited | failed | – |
| unavailable | NO_DEBIT | FAILED | F1_DECLINED_PRE_DEBIT | 0.95 |
| unavailable | DEBITED | FAILED | failed | – |
| DEEMED final | unavailable | PENDING | failed | – |
| PENDING | unavailable | FAILED | F9_CONFLICT | 0.70 |
| unavailable | DEBITED | FAILED | failed | – |
| unavailable | NO_DEBIT | FAILED | F1_DECLINED_PRE_DEBIT | 0.90 |
| SUCCESS final | unavailable | PENDING | F9_CONFLICT | 0.78 |
| unavailable | NO_DEBIT | FAILED | F2_TIMEOUT_PRE_DEBIT | 0.80 |
| unavailable | DEBITED | SUCCESS, debited | F5_DEEMED_SUCCESS | 0.95 |
| FAILED | unavailable | FAILED | F2_TIMEOUT_PRE_DEBIT | 0.72 |

## Simulator vs the real pipeline

485 cases were also run through `pipeline.process_transaction` on a throwaway SQLite database (the code the app runs), with the external world switching between the decision and the live re-check. **485 / 485** gave the same action as the simulator's B1.

Time to a prepared answer (server side, per case):

- tap on a case prepared in the background: median 1.95 ms, p95 2.75 ms
- assembled on demand: median 3.23 ms, p95 5.22 ms

Mock sources answer instantly. Real NPCI and bank calls would add network time, which is why cases are prepared in the background.

## Right payment attached (spec 1.0 sequence)

For 50 simulated users over the HTTP API: chat about an older failed payment, then a new payment fails, the user taps the mic on it and says "issue regarding last payment".

- session bound to the new payment: **50 / 50**
- first reply about the new payment (amount matches): **50 / 50**
- answered in the first turn: 50 / 50
- open + first reply, median 20.8 ms (templates, no LLM, no voice)

In a single-thread support chat, every one of these lands in the old conversation (what we saw in Paytm's chat, spec 1.0). That is by construction, not measured.

## Scenario mix

| Variant | Cases |
|---|---:|
| `f10_claim_amount` | 67 |
| `f10_claim_payee` | 89 |
| `f10_repeat_claimant` | 82 |
| `f1_declined` | 294 |
| `f1_declined+source_outage` | 27 |
| `f1_inside_pending_window` | 69 |
| `f1_inside_pending_window+source_outage` | 3 |
| `f1_late_debit_before_offer` | 64 |
| `f1_late_debit_before_offer+source_outage` | 5 |
| `f2_not_final_yet` | 85 |
| `f2_not_final_yet+source_outage` | 9 |
| `f2_timeout` | 229 |
| `f2_timeout+source_outage` | 11 |
| `f3_pending` | 135 |
| `f3_pending+source_outage` | 8 |
| `f3_pending_record_says_failed` | 68 |
| `f3_pending_record_says_failed+source_outage` | 4 |
| `f3_settling_inside_lag` | 89 |
| `f3_settling_inside_lag+source_outage` | 2 |
| `f4_before_deadline` | 186 |
| `f4_before_deadline+source_outage` | 8 |
| `f4_before_deadline_stale_record` | 67 |
| `f4_before_deadline_stale_record+source_outage` | 4 |
| `f4_deadline_missed` | 108 |
| `f4_deadline_missed+source_outage` | 6 |
| `f4_deadline_missed_stale_record` | 48 |
| `f4_deadline_missed_stale_record+source_outage` | 7 |
| `f4_reversal_lands_before_dispute` | 31 |
| `f5_deemed_success` | 92 |
| `f5_deemed_success+source_outage` | 2 |
| `f5_deemed_success_stale_record` | 108 |
| `f5_deemed_success_stale_record+source_outage` | 8 |
| `f6_bank_down` | 289 |
| `f6_bank_down+source_outage` | 16 |
| `f7_duplicate_debit` | 168 |
| `f7_duplicate_debit+source_outage` | 17 |
| `f8_reversed` | 109 |
| `f8_reversed+source_outage` | 4 |
| `f8_reversed_stale_record` | 157 |
| `f8_reversed_stale_record+source_outage` | 14 |
| `f9_amount_mismatch` | 56 |
| `f9_credit_without_debit` | 52 |
| `f9_npci_success_no_debit` | 49 |
| `f9_record_success_npci_failed` | 54 |

Noise: `p_record_stale` = 0.3, `p_state_change` = 0.1, `p_source_outage` = 0.06, `p_settling` = 0.03
