# Continuous verification of LLM maintenance: protocol v0.4 (draft)

Version 0.4-draft, 6 October 2026. Status: **draft, not frozen; no v0.4 model call has been made.** v0.3 (`PROTOCOL.md`) stays the record of the completed study. v0.4 is a new, separately pre-registered experiment that reuses the frozen stratum-B tasks of v0.3.

## 1. Motivation and disclosure

v0.3 found that verified LLM repairs do not stay clean under quality-neutral maintenance. In stratum B (21 corpus targets, 4 cumulative changes):
- 13/21 repaired and 11/21 original targets gained new God Class or Long Method findings. The repaired-minus-original count was −0.19, 95% CI [−0.68, 0.30], which is equivalent within ±1.
- 3 of 10 Long Method repairs recurred.
- In 10 of 11 God Class targets, the same business methods became Long Methods in both branches. This is an exploratory observation.
- Decision-burden accrual was not lower from the repaired code (H2 replication −0.32 decisions per change).

The v0.3 maintenance agent received a neutral instruction by design (v0.3 Section 6.1). v0.4 asks whether this decay can be prevented, in two ways:
- **design-aware prompting:** guidance in the instruction;
- **analyser-in-the-loop maintenance:** grounded feedback from the static analyser after each change. This is the thesis's hybrid pipeline applied continuously instead of once.

**Disclosure.** v0.4 was designed after the v0.3 outcomes were known, and is motivated by them. Its confirmatory hypotheses concern arms that have never been run, so no outcome of these arms is known. The SESOI is set from v0.3 data before any v0.4 call (Section 7.2).

## 2. Research questions and hypotheses

- **RQ6.1 (continuous verification).** Starting from a verified repair, does analyser-in-the-loop maintenance introduce fewer anti-pattern findings than neutral maintenance?
- **RQ6.2 (design-aware prompting).** Does a design-aware instruction, without analyser feedback, introduce fewer anti-pattern findings than neutral maintenance?
- **RQ6.3 (cost and side effects).** What do the two interventions cost in tokens and correctness, and do they reduce complexity, or merely keep metrics just below the detector thresholds?

Two confirmatory hypotheses, with Holm correction across the two:
- **H3 (RQ6.1):** N_new(R-L) < N_new(R-N).
- **H4 (RQ6.2):** N_new(R-D) < N_new(R-N).

N_new is defined in Section 6. H3 is expected to hold partly by construction, because the loop reports findings from the endpoint detector. Section 6.3 therefore pre-specifies detector-independent checks. H3 is interpreted as debt prevention only if those checks do not show threshold gaming.

## 3. Design

### 3.1 Targets and tasks

- **Targets.** The 21 stratum-B validation targets of v0.3: GC-02, -03, -04, -05, -07, -08, -09, -10, -11, -12 and -13; LM-01, -03, -06, -07, -08, -09, -10, -11, -12 and -13.
- **Tasks.** Their admitted, R2-accepted four-step task sequences, unchanged. The material hashed in `freeze-b1.json` is reused as is: requirements, hidden tests, references and mutants.
- **Starting states.** The baseline original, and the same single accepted repair per target as in v0.3.
- **No new task authoring and no new admission.**

### 3.2 Arms

All arms use the maintenance contract of v0.3 Section 6.1, except where stated:
- the existing `gpt-5.6-sol` deployment;
- strict JSON line patches restricted to the target file;
- a fresh conversation per step;
- at most one retry after an invalid patch or a build failure, carrying compiler diagnostics only;
- hidden tests never shown;
- an output cap of 16,384 tokens per call;
- the context is the type-reference closure of the original file.

| Arm | Start | Instruction | Analyser feedback |
|---|---|---|---|
| O-N | original | neutral (v0.3) | none |
| R-N | repair | neutral (v0.3) | none |
| R-D | repair | neutral plus design guidance (Section 4.1) | none |
| R-L | repair | neutral (v0.3) | after each passing step (Section 4.2) |

- **O-N and R-N replicate the v0.3 branches.** They are re-run rather than reused, so all four arms share the model version, the run period and the instrument. Their agreement with v0.3 is reported descriptively as a drift check.
- **No O-L arm.** On the original code, the analyser would report the seeded anti-pattern itself at the first step, so the loop would perform the repair and be confounded with it.

### 3.3 Order

Within a target, steps alternate across the four arms. The arm order is set by SHA256(`reaccrual-v0.4|target ID|arm`).

## 4. Interventions (fixed text)

### 4.1 Design guidance (R-D)

The following paragraph is appended to the v0.3 system instruction. It is practitioner guidance; it names no tool and no threshold:

> Keep the design clean while you implement the change: keep methods short and focused on one task, keep each class cohesive, and put new behaviour in the class that owns that responsibility instead of growing an existing large method or class. Prefer extending the existing structure over adding branches to a long method.

### 4.2 Analyser loop (R-L)

1. **Normal step.** The step first runs exactly as in R-N.
2. **Trigger.** If the candidate passes every gate (build, API, fail-to-pass, regression), the thesis detector (CLI `analyse`, the same configuration as v0.3) is run on the corpus with the candidate substituted. The loop triggers when the target file has a God Class or Long Method finding that the branch's previous state did not have.
3. **Quality call.** The agent then receives one quality call, in a fresh conversation. It contains the requirement text, the candidate (numbered), and each new finding in the thesis's grounded finding format: type, symbol, line and metrics with thresholds. The instruction is:

   > The static analyser reports the following design findings introduced by your change. Restructure the editable file to remove them. Preserve all behaviour, the public API and the requirement just implemented; edit only the given file.

4. **Acceptance.** The restructured candidate is accepted only if it passes every gate again. Otherwise the pre-quality candidate stands. The step counts as completed either way, because the quality call can never fail a step.
5. **Budget.** At most one quality call per step, with no re-trigger. Its tokens count towards the branch allocation and are reported separately.
6. **Confidentiality.** Hidden-test names, cases and outcomes are never shown.

## 5. Gates and implementation

- **Code.** `stratum_b_run.py` gains `--arms` and the R-D and R-L logic, test-first: prompt rendering per arm, the loop trigger, quality-call acceptance and the per-arm allocation.
- **G-INST.** Unit tests pass. A stub run passes on all 21 targets with the reference provider and with a stub quality call that returns its input unchanged. Every O-N and R-N step completes as in the v0.3 reference check, apart from the 7 known R stub API artefacts. The loop is exercised on at least one target, and the results show it.
- **G-FREEZE.** `freeze-v0.4.json` hashes:
  - the reused task material;
  - the code, the instruction texts above and the settings;
  - this protocol;
  - the starting ledger state.
- **G-LEDGER.** About 1.0M tokens are projected for 4 arms × 21 targets × 4 steps, based on the v0.3 stratum-B usage of about 0.24M per arm. Allowing up to 20% extra for quality calls gives about 1.2M. A ceiling of 1.6M is reserved within the existing 9M authorisation; 3.42M remain. The branch allocation stays at 320k.

## 6. Endpoints

### 6.1 Primary

N_new(b, j) is the number of distinct God Class or Long Method findings (type and symbol) in the target file at state S(b, j) that are absent at S(b, 0). The detector is the CLI analyser with the v0.3 configuration.

For a pairwise comparison of arms a and b, j is the common completed prefix min(L_a, L_b). A target with j = 0 contributes nothing to that comparison and is counted.

### 6.2 Secondary

- **Recurrence:** the target's own anti-pattern type in the R arms, as in v0.3 Section 7.3, per arm.
- **Decision-burden accrual per change**, A_b (v0.3 Section 7.4), and code volume per change, V_b.
- **Correctness:** L_b/K and the first-failure stage.
- **Tokens per completed step**, with the R-L quality calls separate.
- **R-L loop statistics:** triggers, accepted restructurings, and findings left after the quality call.
- **Replication:** O-N versus R-N on N_new and A, compared with the v0.3 values.

### 6.3 Threshold-gaming checks

These are pre-specified and are never shown to any agent:
- **Near-threshold mass:** the share of callables with owned decisions of 8 to 10 (CC just below the Long Method bound), and the share of classes with WMC 40 to 46.
- **Maximum owned callable complexity and file decision burden D** at the final common step.

H3 is read as **debt prevention** only if R-L also has lower or equivalent D accrual than R-N (within the H2 SESOI of 1 decision per change) and a near-threshold share no higher than R-N's by more than 10 percentage points. Otherwise H3 is reported as **metric suppression**.

## 7. Analysis

### 7.1 Confirmatory

For H3 and H4, the paired per-target difference is N_new(R-N) − N_new(arm), oriented so that the hypothesis predicts > 0. The analysis reports:
- the mean with a 95% t-interval;
- a one-sided exact sign-flip p-value;
- Holm correction across H3 and H4 at α = 0.05.

A hypothesis is supported if its Holm-adjusted p is below 0.05 and its interval lies above zero.

### 7.2 Equivalence and SESOI

The SESOI is fixed before any v0.4 call at **0.5 new findings per target**. That is about half the v0.3 R-branch mean of 1.05; the v0.3 median was 1. A non-significant result is called equivalent only if the 90% interval lies within ±0.5. Otherwise it is inconclusive.

### 7.3 Pre-specified sensitivity analyses

1. Exclude GC-03, which the CLI detector does not flag even in its original; see the v0.3 audit.
2. Exclude GC-12 and LM-13, for prior knowledge.
3. God Class versus Long Method targets.
4. Exclude targets where any step used a retry call.
5. The primary endpoint counted at step 4 only, among targets whose arms all complete 4 steps.

## 8. Precision

With 21 targets, a one-sided exact sign-flip can reach p = 1/2^m, where m is the number of non-zero differences. In v0.3, 13/21 repaired targets gained new findings. If R-L removes them in most of those targets, m is about 13, and Holm significance is attainable. H4 depends on how much unguided guidance changes behaviour; an inconclusive H4 is an informative outcome.

## 9. Limitations

- **Construct circularity in R-L.** The loop and the primary endpoint use the same detector, which Section 6.3 mitigates.
- **One wording of the design guidance and one quality call** per step.
- **Same model, tasks and corpus as v0.3.** The tasks are LLM-drafted and R2-reviewed, the corpus is constructed, and the horizon is 4 steps.
- **No O-L arm** (Section 3.2).
- **External validity to industrial code** (stratum A) is not tested in v0.4.

## 10. Deviations and reporting

**Analysis-code fixes, 6 October 2026.** These were made after the run (`validation-v04`, frozen as `freeze-v0.4.json`). The analysis had crashed before writing any summary statistic, and neither fix changes a definition:
1. The near-threshold share of R-D was read at the R-L/R-N common prefix. When R-D had stopped earlier, that raised a missing-state error. R-D's share is descriptive only, and now uses R-D's own common prefix with R-N. The R-L versus R-N gaming check is unchanged.
2. A numpy boolean in the `supported` flag could not be serialised to JSON; it is now converted to a plain boolean.


As in v0.3 Section 13:
- every departure is logged with its date and reason, and whether outcomes had been seen;
- every target and arm is reported, including censored branches and loop statistics;
- v0.3 and v0.4 are reported separately.
