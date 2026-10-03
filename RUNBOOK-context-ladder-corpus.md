# Runbook — supplementary context-ladder run on the constructed corpus

**Audience:** an operator (human or model) executing this run end to end.
**You are executing a frozen protocol, not designing one.** If something does not match what is
written here, stop and record it; do not improvise a fix and continue.

---

## 0. Why this run exists

RQ3's sealed four-level supplement (`experiments/grounding-gpt56-sol-20260728/`) returned
Cochran's Q = 2.478, df 3, p = 0.479, with every adjacent Holm-adjusted p = 1. That null is an
artefact of the instrument, not a finding about context. Three things caused it:

1. **A non-evaluated component decided the outcome.** The pipeline was
   suggest → strict-literal apply, and the applier refused **40/40** God Class recommendations and
   34/40 Obsolete API ones. 79 of 120 assignments (66%) never reached a build. The same model on
   the same corpus scores 310/312 on God Class under direct editing, so the floor was the applier's
   contract, not a limit on the repair.
2. **The manipulated factor never reached the decision point.** Context varied on the suggester;
   the applier always received one file, at every level.
3. **The top rung was nearly a null manipulation.** Full differed from Relational only by project
   metadata, while Obsolete API repairs failed for want of a replacement API that existed one file
   away and was never supplied.

This run replaces that experiment on the **direct-editing** architecture — one evaluated call per
assignment, no applier — with Full redefined as the cross-file declarations the repair needs.

**It is a new, separately frozen experiment.** The sealed supplement is untouched and its
denominators are never pooled with these.

---

## 1. Non-negotiables

- **No retries.** API failure, parse failure, build failure and detector non-resolution are
  *outcomes*. They stay in the denominator. Never re-run an assignment to get a better result.
- **Never inspect outcomes before the campaign is sealed.** Do not open traces, count resolutions,
  or run analysis mid-run. The run is complete or it is not.
- **Never re-run a completed assignment.** The ledger is authoritative; resume skips what it records.
- **Do not edit** `ContextLadder`, `ContextLadderPrompt`, `ContextBuilder`, `FactorialSingleShotRunner`
  or any manifest during the run. The campaign verifies the ladder hash and will refuse to start on
  drift — that guard exists because a definition edited after freezing silently invalidates the run.
- **Record every deviation** in `DEVIATIONS.md` inside the experiment directory, as it happens, with
  what was affected. A recorded deviation is a finding; an unrecorded one is a fabrication.

---

## 2. Preconditions

| Requirement | Check |
|---|---|
| .NET 10 SDK | `dotnet --version` |
| Repo at the frozen revision | `git rev-parse --short HEAD` → record it; built at `a2c787d` |
| Tests green | `dotnet test src/HybridLens.Tests/HybridLens.Tests.csproj` → **141 passed** |
| Corpus present | `Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln`, ground-truth `corpus_version: v2.0` |
| Corpus pristine | `git -C Z:\GitHub\hybrid-pipeline-corpus status --short` → clean |
| Model configured | `src/HybridLens.CLI/appsettings.local.json` defines `gpt-5.6-sol` |

No applier model is needed. This architecture has none.

---

## 3. Pre-registered design — frozen before any model call

Copy this section verbatim into the experiment's `PROTOCOL.md` before step 1.

- **Population:** all 36 detector-confirmed corpus v2.0 targets — 13 God Class, 13 Long Method,
  10 Obsolete API Usage.
- **Factor:** context level, four levels — Minimal, Structural, Relational, Full.
- **Repetitions:** 3 per target-level cell.
- **Volume:** 36 × 4 × 3 = **432 assignments**, one evaluated-model call each.
- **Architecture:** direct editing, single-shot. No applier. Visible generated tests **OFF**
  throughout — the supplement disabled them and adding the factor here would confound the dose.
- **Ladder:** `ladder-v2.0.0`, SHA-256
  `8c5bcdb50d61a13d439dbbcb9a7a5eb46270349d869bc254ab5b69c13a4dd86f`.
  Full = Relational + declaring source of every external type the target references, capped at
  8 files / 60,000 characters, ordered ordinally by relative path then declaring type name.
- **Prompt family:** `ladder-v1.0.0` (`ContextLadderPrompt`).
- **Starting state:** pristine corpus for every assignment, in an isolated working copy.
- **Retry policy:** none.

### Outcomes

**Primary:** verified repair — the edit builds **and** the triggering detector condition no longer
fires. Matched four-level comparison via Cochran's Q over target blocks; prespecified adjacent
contrast **Full − Relational**, since the cross-file rung is the one the mechanism predicts.
Remaining adjacent contrasts secondary, exact McNemar with Holm adjustment.

**Secondary:** ordinal repair ladder (`build_fails < builds_unresolved < resolved`); private
Layer 3 behavioural outcome; whole-solution Layer 1/2 quality change; prompt size, tokens and cost
per level; **cross-file truncation rate per level**.

### Pre-registered stratifications

1. **Successor availability (Obsolete API only).** Only **4 of 10** Obsolete API targets have an
   in-corpus successor (`SmsApiV2`, `LabelApiV2`, `MailApiV2`, `NotifyApiV2`). The other 6 carry
   deprecation notices explicitly stating no direct replacement (*"Removed; no replacement"*,
   *"Use IRateProvider"*, *"Use ICalendarWriter"*, *"Use IDocumentWriter"*), which §4.5.5 confirms
   is deliberate. The cross-file rung can only supply a successor where one exists, so the sharpest
   mechanism claim is testable on **n = 4**, not 10. **Verify this split against the fresh baseline
   in step 2 and record it before running.**
2. **Ceiling controls.** God Class and Long Method sit at 99.4% / 88.5% strict success under direct
   editing in the v2 factorial. They are pre-registered as ceiling controls: no movement is the
   expected result and is not a failed test. Report the MDE so the null is bounded, not open.

### Known threat to record now

A repair can resolve the detector **without migrating**. In the feasibility probe,
`CurrencyConverter` at Structural "resolved" by binding the same obsolete implementation through a
delegate so the detector's symbol resolution no longer saw a direct `[Obsolete]` reference. That is
detector evasion, and it is the §4.8 threshold-crossing threat. **Do not report detector resolution
alone as repair for Obsolete API.** Grade each resolved Obsolete API repair as
`migrated | evaded | ambiguous` from `parsed_suggested_fix` / the edited file, after sealing, and
report it beside the Layer 3 smoke result.

---

## 4. Procedure

Work in a new directory, `EXP=experiments/context-ladder-corpus-v2-<YYYYMMDD>`.

### Step 1 — Fresh baseline (do **not** reuse an existing one)

The baseline at `experiments/grounding-gpt56-sol-20260728/preflight/static-output.json` is
**corpus v1.0 and has 30 findings**. The corpus is now v2.0 with 36. Using the old one silently
drops 6 targets and may carry stale coordinates.

```bash
dotnet run --project src/HybridLens.CLI -- analyse \
  --target Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln \
  --dry-run --format json --severity Warning \
  --output $EXP/preflight/baseline.json
```

**Expect:** `Loaded 11 project(s).` and `Found 36 finding(s)`. Confirm the split is
13 godClass / 13 longMethod / 10 obsoleteApiUsage. **If it is not 36, stop.** No model call has
been made, so there is nothing to unwind — diagnose the corpus state first.

### Step 2 — Verify the successor split

For each of the 10 Obsolete API targets, read the file declaring the deprecated type (the
`Legacy/*Api.cs` in the same project) and record whether it declares a `*V2` successor. Write the
result to `$EXP/preflight/SUCCESSOR_SPLIT.json` as `{target, successor_type|null, obsolete_message}`.

**Expect 4 with a successor, 6 without.** If the numbers differ from §3, record the discrepancy in
`DEVIATIONS.md` and use the observed split — the corpus is authoritative, this runbook is not.

### Step 3 — Build the manifest

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-manifest \
  --from $EXP/preflight/baseline.json \
  --target Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln \
  --model gpt-5.6-sol \
  --code-revision $(git rev-parse --short HEAD) \
  --seed <CHOOSE ONCE AND RECORD> \
  --runs 3 \
  --out $EXP/ladder-manifest.json
```

**Expect:**
```
Assignments: 432 (36 targets x 3 repetitions x 4 levels)
Ladder:      ladder-v2.0.0 (8c5bcdb5...)
Cross-file:  108 assignments carry declarations; N were capped
```
108 = 36 targets × 3 reps × the single Full level. Record `N` capped — truncation is a reported
outcome. The command refuses to overwrite an existing manifest; that is intentional.

### Step 4 — Preflight

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-campaign \
  --manifest $EXP/ladder-manifest.json --out $EXP/campaign --preflight-only
```

**Expect:** `Context ladder preflight passed; no model call made.` This validates the manifest hash,
the ladder hash, every pristine source hash, block balance and the cross-file payload hashes.

### Step 5 — Freeze

Record in `$EXP/PRE_RUN_AUDIT.json` and `$EXP/PRE_RUN_SHA256SUMS.txt`, before the first call:
repo revision, manifest SHA-256, ladder version and hash, prompt version, seed, baseline SHA-256,
corpus revision, model deployment identifier, and the successor split from step 2. Commit the
protocol and the pre-run seal **before** step 6. Follow the layout of
`experiments/grounding-gpt56-sol-20260728/` — that directory is the reference for what a sealed
experiment looks like here.

### Step 6 — Run

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-campaign \
  --manifest $EXP/ladder-manifest.json --out $EXP/campaign
```

Roughly **6 hours** and **$8–10** of tokens (scaled from a 12-assignment probe: 6,637 input /
9,611 output tokens). Each assignment copies the corpus, makes one call, builds, and remeasures.

The run is crash-safe. To resume, re-issue the identical command: the ledger is replayed, completed
assignment trace hashes are re-verified, and completed work is never repeated. Use `--stop-after N`
only if you deliberately want to run in slices.

### Step 7 — Seal, then measure behaviour

Only after every assignment has terminated:

1. Seal the campaign — `POST_RUN_SHA256SUMS.txt` over traces, final-sources and the ledger.
2. Private Layer 3 (behavioural equivalence for God Class / Long Method, smoke oracle for
   Obsolete API):
   ```bash
   dotnet run --project src/HybridLens.CLI -- private-layer3 \
     --artifacts $EXP/campaign/final-sources --target <corpus.sln> \
     --manifest <oracle manifest version> --out $EXP/private-results/layer3.jsonl \
     --parallelism 4
   ```
3. Whole-solution quality:
   ```bash
   dotnet run --project src/HybridLens.CLI -- external-quality \
     --artifacts $EXP/campaign/final-sources --out $EXP/quality-results/layer2.jsonl \
     --parallelism 4
   ```
4. `FINAL_SEAL.json` + `FINAL_SHA256SUMS.txt` over everything, including the runner logs — the
   sealed v2 factorial includes its `runner-*.log` files in the manifest and so should this one.

### Step 8 — Analysis

Write `analysis/context_ladder_analysis.py` with tests under `analysis/tests/`. Reuse the estimator
and convergence-diagnostic pattern in `analysis/factorial_glmm.py`; note its
`validate_model_ready_data` asserts 24 attempts per instance, so the ladder needs its own validator
(4 levels × 3 reps = 12). Report everything listed under **Outcomes** in §3, plus the
`migrated | evaded | ambiguous` grading.

---

## 5. Failure modes

| Symptom | Meaning | Action |
|---|---|---|
| `incomplete assignment trace already exists` | A prior run died mid-assignment | Move that trace to `campaign/quarantine/`, record in `DEVIATIONS.md`, resume. Do **not** delete it. |
| `completed assignment trace hash changed` | A sealed trace was modified | **Stop.** The campaign's integrity is compromised; do not resume until you know why. |
| `context ladder definition drift` | Compiled ladder ≠ manifest hash | The code changed after freezing. Restore the frozen revision. Never re-freeze the manifest to match new code. |
| `production_build_failed` on an assignment | The model's edit did not compile | This is a valid outcome. Leave it. |
| API failure / parse failure | Model or contract failure | Valid outcome, stays in the denominator. No retry. |
| Fewer than 36 findings at step 1 | Corpus is not v2.0 or is dirty | Stop before step 3. |

---

## 6. What must be recorded

- Seed, repo revision, corpus revision, model deployment identifier
- Manifest SHA-256, ladder version + hash, prompt version
- Successor split (step 2)
- Cross-file truncation count and which files were dropped
- Every deviation, as it happens
- Total tokens and cost per level

---

## 7. What not to conclude

- **Detector-resolved is not behaviour-preserving.** It means built + detector silent. Behavioural
  claims require the Layer 3 result, and for Obsolete API that oracle is a smoke check only —
  §4.5.5 is explicit that these migrations are behaviour-modifying by construction.
- **God Class / Long Method not moving is the expected result**, not evidence that context is
  irrelevant. Report the MDE.
- **Do not pool** these denominators with the sealed supplement or the confirmatory factorial. The
  sealed supplement is an informal architecture comparison — same model, same corpus family, same
  detector, differing in delivery mechanism — and should be described that way, not as a
  controlled contrast.
- **n = 4 for the sharpest mechanism claim.** Say so plainly wherever it is reported.

---

## Appendix — feasibility probe already run

12 assignments over 3 Obsolete API targets, 1 repetition, at revision `a2c787d`. Useful as an
expected-behaviour reference; **not** part of this experiment's denominators.

| target | minimal | structural | relational | full |
|---|---|---|---|---|
| EmailClient (MailApiV2 exists) | unresolved | unresolved | unresolved | resolved |
| CurrencyConverter (no successor) | unresolved | resolved* | unresolved | resolved |
| ReminderSender (NotifyApiV2 exists) | build fails | unresolved | unresolved | resolved |

\* the detector-evasion case described in §3.

Verified there: the rendered Full prompt carries `## Referenced declarations` and the Legacy file;
`repair_applicable == false` in **0 of 12**, against 34/40 in the sealed supplement; mean prompt
size 780 → 1,003 → 1,589 → 3,026 characters across the four levels.

Three targets and one repetition cannot support an inference. The probe establishes that the
instrument works, and nothing about the effect.
