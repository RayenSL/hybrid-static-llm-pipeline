# Cross-model replication of continuous verification: protocol v0.6

Version 0.6, 6 October 2026. Status: **approved by the thesis author and frozen on 6 October 2026, before any v0.6 model call other than the access check of Section 5. Amendment 0.6.1 (reply normalisation, Section 7) was made after 7 of 21 targets of a first run, and the run was restarted from scratch under a new freeze.** v0.4 (`PROTOCOL-v0.4.md`) remains the record of the original study. This protocol changes nothing in v0.4's tasks, prompts, gates or analysis; it changes the maintenance model.

## 1. Motivation and disclosure

v0.4 found that feeding the static analyser's findings back after each maintenance change removed all newly introduced God Class and Long Method findings (0 of 21 targets, against 12 of 21 under neutral maintenance), while design guidance in the prompt had a small, fragile effect. Every v0.3-v0.5 result rests on one model, `gpt-5.6-sol`. v0.6 asks whether the v0.4 findings hold for a frontier model from a different vendor.

- **Model.** Claude Opus 5.5, the Azure deployment `claude-opus-5-5` on the same Azure resource as `gpt-5.6-sol`. The deployment does not support the chat-completions route; it is served through the Anthropic-compatible Messages route of that resource. The code stays inside the same Azure tenant.
- **Why this model.** It is a top-tier model from another lab, so a difference in results cannot be attributed to a capability gap (a mid-tier model could), and it also tests the objection that stronger models would not need the loop.
- **Task-author overlap.** The 21 task sequences (requirements, hidden tests, references and mutants) were drafted by Claude Sonnet 5.5 subagents and reviewed by R2. Opus shares the family, so it may be more familiar with the style of the tasks, which could raise its absolute completion rate. The primary contrasts (loop versus no loop; guidance versus none) compare two arms of the same model on identical tasks, so such an effect is expected to cancel; it is a limitation for the absolute levels.
- **Analyst disclosure.** The analysis assistant that drafted the tasks, wrote the runner and chose this model is itself a Claude model.
- **Design order.** v0.6 was designed after the v0.4 results were known. Its hypotheses are replication hypotheses with a criterion fixed before any call (Section 2).

## 2. Hypotheses and replication criterion

The hypotheses are v0.4's, applied to the new model, with the same definitions of N_new, the same arms and the same Holm correction across the pair:
- **H3-O (analyser loop):** N_new(R-N) − N_new(R-L) > 0 on Opus 5.5.
- **H4-O (design guidance):** N_new(R-N) − N_new(R-D) > 0 on Opus 5.5.

**Replication criterion, fixed before any call.** A hypothesis replicates when, on Opus 5.5, its Holm-adjusted one-sided exact sign-flip p-value is below 0.05 and its 95% interval lies above zero (v0.4 Section 7.1). A result with the right sign that fails this criterion is reported as not replicated, with its interval; it is not interpreted as a failure of v0.4.

**Not a test of equality of effects.** The two models' effects are reported side by side with their intervals. No pooled estimate and no test of heterogeneity between models is made, because two models cannot support one.

## 3. Design

Identical to v0.4 (Sections 3 to 7), stated here so that no reading of v0.4 is needed to run v0.6:
- the 21 stratum-B targets, with their admitted task sequences and the starting states, unchanged and hash-checked against `freeze-b1.json`;
- the four arms O-N, R-N, R-D and R-L, with the instruction, design-guidance and quality-call texts of v0.4 Sections 4.1 and 4.2 verbatim, and the arm order of `SHA256(reaccrual-v0.4 | target | arm)`;
- the maintenance contract of v0.3 Section 6.1: a fresh conversation per step, strict JSON line patches restricted to the target file, at most one call plus one retry after an invalid patch or a build failure with compiler diagnostics, hidden tests never shown, an output cap of 16,384 tokens per call and an allocation of 320,000 tokens per branch;
- the gates, endpoints, sensitivity analyses and the threshold-gaming checks of v0.4 Sections 5 to 7, computed by the unchanged analysis script.

### 3.1 Differences that cannot be avoided

| Item | v0.4 | v0.6 |
|---|---|---|
| Model and route | `gpt-5.6-sol`, Azure chat completions | `claude-opus-5-5`, same Azure resource, Messages route |
| Sampling | temperature 1, from the deployment entry | temperature 1, set explicitly for the run and recorded in the freeze, so that sampling is matched. The Opus entry has no temperature of its own, and the shared setting (0.1) would otherwise apply |
| Reasoning | internal reasoning, reported per call | adaptive: the deployment reports thinking tokens on some calls (none in the access check, 114 of 468 output tokens on one call of the first run). The run does not set extended thinking; reasoning tokens are recorded per call |
| Reply format | pure JSON | a short prose explanation, then one fenced JSON block (observed in the access check). The edit schema and file scope are unchanged; if a reply holds exactly one fenced block, that block is used; otherwise, if it holds one JSON object that begins with the key `edits`, that object is used and any prose before or after it is ignored (Amendment 0.6.1). Such replies are marked as normalised. Replies with several fenced blocks, with a broken or absent edit object, and pure JSON replies go to the strict parser unchanged. The share of normalised replies is reported. Pure JSON replies, and so all `gpt-5.6-sol` replies, are not affected |
| Token estimate | bytes / 3.5 per token, calibrated on the OpenAI tokeniser | the access check showed 5,451 reported input tokens against an estimate of 4,964, so the ledger reservation for this model is widened by a factor of 1.25. Provider-reported usage is the ledger value |
| Pacing | 236,000 tokens per minute | the same client-side limit is applied as a conservative bound, and 429 responses are retried with a wait. The Opus deployment's own quota is not known |

These differences are part of the model comparison and are not controlled. The effect of enabling extended thinking is not examined.

## 4. Endpoints and analysis

- **Confirmatory:** H3-O and H4-O (Section 2), with the SESOI of 0.5 new findings per target for equivalence statements.
- **Secondary and descriptive:** exactly those of v0.4 Section 6.2: recurrence, decision-burden and code-volume accrual, correctness (the share of completed steps), tokens per completed step with the quality calls shown separately, the analyser-loop statistics, and the replication of O-N versus R-N.
- **Gaming checks:** v0.4 Section 6.3, with the same reading rule for H3-O (debt prevention or metric suppression).
- **Cross-model table (descriptive):** the effects of the loop and of guidance, completion, and the tokens per completed step for the two models, with their intervals.
- **Sensitivity analyses:** the five of v0.4 Section 7.3.

The analysis uses `v04_analyze.py` unchanged, on the v0.6 run directory.

## 5. Gates and implementation

- **G-ACCESS.** The `claude-opus-5-5` deployment answers through the existing Azure route. One call with a corpus quality-call prompt (public code, no industrial code) must return provider-reported usage and JSON line patches that parse and apply. The check also compares the prompt-size estimate with the reported input tokens. Any estimate that falls below the reported usage is reported, and the reservation margin is adjusted before the freeze if needed.
- **Access check, done on 6 October 2026.** One call with a public-corpus quality-call prompt (no industrial code) returned in 6.9 seconds with usage reported (5,451 input and 672 output tokens, 0 thinking tokens, finish reason `end_turn`). The reply was prose plus one fenced JSON block, which the normalisation rule above turns into a patch that parses and applies. The token estimate was 9% below the reported input, which led to the widened reservation.
- **G-INST.** The runner has unit tests. The stub run of v0.4 is repeated and must give the same result with the model and temperature options present.
- **G-LEDGER.** About 1.0-1.5M tokens are projected: v0.4 used 1.04M on the first model, and the new model's token counts may differ. A ceiling of 1.6M is reserved within the existing authorisation.
- **G-FREEZE.** `freeze-v0.6-opus.json` hashes the same inputs as `freeze-v0.4.json`, plus this protocol, the code, the settings and the model key.
- **Approval.** The thesis author approves this protocol before the freeze.

## 6. Limitations

- One additional model. Two models, from two vendors, are a replication, not a population of models.
- The task-author overlap of Section 1, the unmatched sampling and reasoning settings of Section 3.1, and the other limitations of v0.4 (constructed corpus, LLM-drafted tasks, a loop that uses the same detector as its endpoint, four-step horizon) all apply.
- Anti-pattern findings are a proxy for debt, with no downstream effort or defect measure.

## 7. Deviations and reporting

As in v0.3 Section 13: every departure is logged with its date and reason, and whether outcomes had been seen; every target and arm is reported, including censored branches; v0.3, v0.4, v0.5 and v0.6 are reported separately.

**Deviation 1, 6 October 2026: reply normalisation (Amendment 0.6.1); outcomes of the first run had been partly seen.**
- **What happened.** The first run stopped after 7 of 21 targets (126 steps: 120 completed, 5 failures at the API gate, 1 `invalid_patch`). The `invalid_patch` was an instrument gap: after a build failure, the retry reply was an explanation followed by a raw, unfenced JSON edit object, and the normalisation of Section 3.1 handled only fenced blocks. A valid edit was counted as invalid.
- **Change.** The normalisation also accepts one raw JSON edit object with surrounding prose (Section 3.1). It concerns the format of the reply, not its content, and applies to every reply alike. Pure JSON replies, and so all `gpt-5.6-sol` replies, are unaffected.
- **Handling.** The first run is kept, unused, as `validation-v06-opus-aborted-1`, and its tokens are charged. The run was restarted from the first target under a new freeze, so that every target is run with one version of the instrument. No result of the first run is used.
- **Observation.** In the first run, 4 of 14 early replies, and 48 of 134 first calls overall, needed the fenced-block normalisation, so reply format is a substantive difference between the two models.

