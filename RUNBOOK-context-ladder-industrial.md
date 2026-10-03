# Runbook — industrial context-ladder run on Ibis.Besteksadministratie

**Audience:** an operator (human or model) executing this run end to end.
**Companion document:** `RUNBOOK-context-ladder-corpus.md`. Read §0–§1 of that file first; the
rationale for the experiment is shared and is not repeated here. This document covers only what is
different, and almost everything operational is different.

**This experiment is descriptive.** It has nine targets. It does not test a hypothesis, and §7 says
what may not be claimed from it.

---

## 0. Stop conditions — resolve these before anything else

### 0.1 Disclosure (blocking)

`RunRecord.RawUserPrompt`, `RawSystemPrompt` and every `campaign/final-sources` artefact embed
**whole source files from a proprietary Aceve codebase**. 108 assignments produce 108 traces plus
108 materialised sources. The pipeline repository is **public**.

Decide before the first model call, and record the decision in the protocol:

- a private repository or submodule for `experiments/ibis-*`, or
- commit only hashes, ledger and derived results, with traces gitignored.

Scrubbing afterwards is not an option: it breaks the SHA-256 seals that make the run auditable.

### 0.2 The oracle is not version controlled (blocking)

`z:\rayen\industrial-probe\` is not a git repository. The 90-driver oracle, its goldens, the
band-agreement artefacts and both generator scripts exist only on disk. Back it up or place it under
version control — subject to 0.1 — before running anything that depends on it.

### 0.3 BES-LM-08 is unconfirmed (non-blocking, must be recorded)

`BES-LM-08` (`ProjectManagerLinePeriod.GetOverValue`) was selected mechanically from the filtered
pool. Its `is_long_method` is `pending_review` in `besteks-targets.json`. Either have a reader judge
it and record the judgement, or run with it and report the label as unconfirmed. Do not quietly
promote it to `yes`.

---

## 1. Two feasibility risks specific to this codebase

### 1.1 Output-token ceiling — verify before committing to a full run

The direct-edit contract requires the model to return the **complete edited file**. Corpus files are
small; these are not.

| target file | chars | ≈ output tokens required |
|---|---|---|
| `ProjectManagerProject.cs` (BES-LM-08) | 74,259 | ~20,600 |
| `ReportPeriodState.cs` (BES-LM-04) | 58,723 | ~16,300 |
| `Extensions.cs` (BES-LM-01) | 47,300 | ~13,100 |
| `ProjectManager.cs` (BES-LM-02) | 45,164 | ~12,500 |
| `ReportFinalStatement.cs` (BES-LM-03) | 32,187 | ~8,900 |
| `AttachmentService.cs` (BES-LM-07) | 29,693 | ~8,200 |
| `ReportHelpers.cs` (BES-GC-01) | 19,860 | ~5,500 |
| `ImageMetadataService.cs` (BES-LM-05) | 3,807 | ~1,100 |
| `ReportResolverFactory.cs` (BES-LM-06) | 3,327 | ~900 |

Mean pristine source is **34,924 characters**, against roughly 1–3k for the whole corpus prompt. If
the deployment's maximum output is below ~21k tokens, every `BES-LM-08` assignment returns truncated
JSON and fails to parse — a uniform artefact, not a result.

**Run the probe in §4 against `BES-LM-08` first.** If it parse-fails at every level, stop and
reconsider the contract (a patch-based rather than whole-file response) rather than recording 12
parse failures as outcomes.

### 1.2 Truncation is real here

The corpus capped nothing. Ibis caps 12 of 27 Full assignments at 8 files / 60,000 characters:

| target | files supplied | chars | dropped |
|---|---|---|---|
| `ReportResolverFactory.Resolve` | 8 | 18,153 | **13** |
| `ReportPeriodState.GetReportPeriodStateProductionModel` | 6 | 50,746 | 3 |
| `ReportFinalStatement.GetReportOverUnderTotalsModel` | 6 | 50,016 | 2 |
| `ProjectManager.GetProductionDeclarationFineTotal` | 6 | 4,866 | 1 |
| `ProjectManagerLinePeriod.GetOverValue` | 3 | 48,683 | 0 |
| `AttachmentService.ValidFileForType` | 2 | 8,665 | 0 |
| `ReportHelpers` | 2 | 1,057 | 0 |
| `Extensions.AsDbXml` | 0 | 0 | 0 |
| `ImageMetadataService.GetGPSCoordinates` | 0 | 0 | 0 |

Two targets receive **no** cross-file payload at all, so for them Full ≡ Relational: `AsDbXml` is a
static extension with no project-declared dependencies, and `GetGPSCoordinates` takes ImageSharp
types that live in a metadata reference and have no declaring syntax. **Report those two as
structurally unable to show a Full effect** rather than as evidence that Full does not help.

Truncation rate per level is a reported outcome. Do not raise the cap to make it go away — that
changes the ladder hash and invalidates comparability with the corpus run.

---

## 2. Preconditions

| Requirement | Check |
|---|---|
| Repo revision | `git rev-parse --short HEAD`; record it |
| Tests green | `dotnet test src/HybridLens.Tests/HybridLens.Tests.csproj` → 141 passed |
| Solution builds | `dotnet build Ibis.Besteksadministratie.sln -c Debug --no-restore -p:NuGetAudit=false` → 0 errors, ~16s |
| Oracle passes on pristine | `dotnet run --project layer3-besteks/Characterization.csproj --no-build -v quiet -- --check layer3-besteks/golden` → **90 PASS, exit 0** |
| Model configured | `gpt-5.6-sol` in `appsettings.local.json` |

**Both build flags are mandatory.** The command line has no credentials for the private NuGet feed:
`--no-restore` uses the package cache a prior IDE restore populated, and `NuGetAudit=false` stops the
vulnerability check reaching the Telerik feed. Remaining warnings are licence notices.

---

## 3. Pre-registered design

- **Population:** the 9 hand-confirmed targets in `z:\rayen\industrial-probe\besteks-targets.json` —
  8 Long Method (`BES-LM-01`…`08`) and 1 God Class (`BES-GC-01`).
- **Volume:** 9 × 4 levels × 3 repetitions = **108 assignments**.
- **Ladder:** `ladder-v2.0.0`, SHA-256
  `8c5bcdb50d61a13d439dbbcb9a7a5eb46270349d869bc254ab5b69c13a4dd86f` — identical to the corpus run,
  which is what makes the two comparable in *definition* even though the payloads differ in size.
- **Architecture:** direct editing, single-shot, no applier. Visible tests OFF.
- **Independence:** at most one target per class, already enforced during labelling. Nine
  independent targets, no clustering needed.
- **Retry policy:** none.

### Declared before the run

- **`BES-GC-01` is n = 1.** Report it as a single case, never as a God Class stratum.
- **`BES-LM-06` is a reader-rejected control** (`is_long_method: no`): 26 lines whose complexity is
  entirely switch arms. If a repair model edits it at all, that is the informative observation.
- **`BES-LM-06`'s oracle has limited resolving power, structurally.** `CreateInstance<T>` runs
  through `ServiceActivator.GetScope()`, a static locator with no container in the harness, so all
  eighteen mapped switch arms fail identically. The oracle distinguishes four outcomes but **cannot
  tell the arms apart**; a repair permuting them would pass. Say so wherever it is reported.
- **`Extensions.AsDbXml` and `ImageMetadataService.GetGPSCoordinates` receive no Full payload**
  (§1.2).
- **Detection recall and precision must not be claimed on this codebase.** There is no exhaustive
  truth set, so a finding outside the admitted list can be judged neither correct nor spurious.
  Report repair outcomes only, over targets described as detector-selected.

---

## 4. Procedure

`EXP=experiments/ibis-context-ladder-<YYYYMMDD>` — subject to §0.1, this may need to live outside
the public repository.

### Step 1 — Fresh baseline

```bash
dotnet run --project src/HybridLens.CLI -- analyse \
  --target Z:\GitHub\Ibis.Besteksadministratie\Ibis.Besteksadministratie.sln \
  --dry-run --format json --severity Warning \
  --output $EXP/preflight/baseline.json
```

**Expect:** `Loaded 11 project(s).` and `Found 128 finding(s)` — 118 Long Method, 6 God Class,
2 Obsolete API (exit code 1 is the severity gate, not a failure). Only 11 of 25 projects load; the
unloaded set is mostly test, e2e and database projects. Record that as a population limitation.

### Step 2 — Admitted list

Generate from `besteks-targets.json`, one entry per target:

```json
[ {"id": "BES-LM-01", "file": "Source\\WebCore\\...\\Extensions.cs",
   "symbol": "Extensions.AsDbXml", "line": 429}, ... ]
```

**`line` is mandatory wherever a symbol is not unique.** `Extensions.AsDbXml` has **six overloads**,
all detector-flagged; without a line, the admitted list silently expands 9 targets into 14 and puts
six of them in one class, breaking the independence rule. `BES-LM-03` and `BES-LM-04` have no line
recorded and their symbols are unique, so omit `line` for those two only — the matcher treats a
missing line as a wildcard. The command refuses to run when the admitted count and the matched count
disagree.

### Step 3 — Manifest

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-manifest \
  --from $EXP/preflight/baseline.json \
  --target Z:\GitHub\Ibis.Besteksadministratie\Ibis.Besteksadministratie.sln \
  --admitted $EXP/preflight/admitted.json \
  --model gpt-5.6-sol --code-revision $(git rev-parse --short HEAD) \
  --seed <CHOOSE ONCE AND RECORD> --runs 3 \
  --out $EXP/ladder-manifest.json
```

**Expect exactly:**
```
Assignments: 108 (9 targets x 3 repetitions x 4 levels)
Cross-file:  21 assignments carry declarations; 12 were capped
```
Any other numbers mean the admitted list or the baseline is not what this runbook assumes. **Stop.**

Loading the Ibis workspace takes a few minutes; that is expected.

### Step 4 — Preflight, then freeze

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-campaign \
  --manifest $EXP/ladder-manifest.json --out $EXP/campaign --preflight-only
```

Then record `PRE_RUN_AUDIT.json` and `PRE_RUN_SHA256SUMS.txt`: repo revision, manifest hash, ladder
version and hash, prompt version, seed, baseline hash, Ibis revision, model deployment, the
disclosure decision from §0.1, the `BES-LM-08` label status, and the SHA-256 of all 90 goldens.

### Step 5 — Feasibility probe (**do this before the full run**)

Build a second manifest restricted to `BES-LM-08` and `BES-LM-06` — the largest file and the
smallest — with `--runs 1`, then:

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-campaign \
  --manifest $EXP/probe-manifest.json --out $EXP/probe --stop-after 8
```

Check, in order:

1. **No parse failures on `BES-LM-08`.** If all four fail, §1.1 has bitten. Stop.
2. The rendered Full prompt contains `## Referenced declarations`, and `context_truncated` is set
   where §1.2 predicts.
3. Measure actual tokens and wall clock per assignment, and extrapolate before spending the rest.

The probe is **not** part of the experiment's denominators. Keep it in a separate directory and say
so in the protocol.

### Step 6 — Run

```bash
dotnet run --project src/HybridLens.CLI -- context-ladder-campaign \
  --manifest $EXP/ladder-manifest.json --out $EXP/campaign
```

Rough expectation, to be replaced by the probe's measurement: input ~10k tokens per assignment and
output dominated by the returned file at ~9k mean, so on the order of **$25–40** and **3–5 hours**.
Output is the dominant cost here, the reverse of the corpus run.

Crash-safe and resumable: re-issue the identical command.

### Step 7 — Seal, then measure behaviour

Seal the campaign first. Then:

```bash
dotnet run --project src/HybridLens.CLI -- external-oracle \
  --artifacts $EXP/campaign/final-sources \
  --target Z:\GitHub\Ibis.Besteksadministratie\Ibis.Besteksadministratie.sln \
  --harness z:\rayen\industrial-probe\layer3-besteks\Characterization.csproj \
  --golden  z:\rayen\industrial-probe\layer3-besteks\golden \
  --harness-prop -p:ProductRoot={WORKING_ROOT} \
  --build-arg --no-restore --build-arg -p:NuGetAudit=false \
  --working-copy-skip bin --working-copy-skip .git --working-copy-skip .vs --working-copy-skip .idea \
  --out $EXP/private-results/external-oracle.jsonl
```

Three things about this command are load-bearing:

- **`obj` must NOT be skipped.** A harness built with `--no-restore` needs `project.assets.json`;
  without it MSBuild stops at NETSDK1004 and the failure is misrecorded as `public_contract_change`.
  The evaluator refuses this combination outright, which is the guard working.
- **`{WORKING_ROOT}`** is substituted with the isolated copy. Without it the harness measures
  pristine code and every artefact passes.
- **There is no `--parallelism` on this command.** Unlike `private-layer3` and `external-quality`,
  `ExternalOracleEvaluator.EvaluateDirectoryAsync` is still a sequential loop. 108 artefacts, each a
  full tree copy plus harness build, is the longest step in the run — plan for hours, or add
  parallelism first, mirroring commit `f3c1900`.

Then `external-quality` for Layer 2, and a `FINAL_SEAL.json` over everything.

### Step 8 — Analysis

Report: the ordinal ladder by level; three-valued oracle outcomes including `public_contract_change`
(Extract Method on a God Class will trigger it legitimately); **truncation rate per level**; prompt
size, tokens and cost per level; and per-target detail, since with nine targets the per-target table
*is* the result.

---

## 5. Failure modes

Everything in the corpus runbook's §5 applies, plus:

| Symptom | Meaning | Action |
|---|---|---|
| Parse failure concentrated on large files | §1.1 output ceiling | Stop; do not record as outcomes |
| `NETSDK1004` during oracle evaluation | `obj` was skipped | Fix the skip list; re-evaluate |
| Every artefact `behaviour_preserved` | `{WORKING_ROOT}` not substituted | Harness measured pristine code; re-evaluate |
| Oracle reports fewer than 90 drivers | Golden set incomplete | Re-check against `golden-v1-6driver` — you may be pointing at the v1 directory |
| Manifest yields ≠ 108 assignments | Admitted list wrong (§2) | Stop |

---

## 6. Do not compare against `probe-run/`

`z:\rayen\industrial-probe\probe-run\` holds a completed 36-assignment grounded-versus-ungrounded
run scored against the **v1 six-driver oracle**, preserved at `golden-v1-6driver`. The 90-driver
instrument is a different measuring device: 31 of 36 artefacts scored `behaviour_preserved` against
one driver per target, and that number is not comparable with anything measured at ten. Re-score it
under v2 before setting any of its results beside this run's.

---

## 7. What may not be claimed

- **No hypothesis test.** Nine targets, and the binding constraint is discordant pairs, not n. The
  exact sign-flip floor sits above conventional thresholds whatever the data show. Report effect
  sizes, per-target detail and mechanism; report no p-value.
- **`BES-GC-01` is one case**, not a God Class result.
- **No detection recall or precision** on this codebase.
- **Do not pool** these denominators with the corpus ladder, the confirmatory factorial or the
  sealed supplement. The corpus run is the mechanism experiment with a matched control; this is an
  ecological-validity probe at realistic dependency depth. The shared ladder definition makes the
  two commensurable in kind, not in magnitude — a Full rung here supplies up to 50k characters
  across six files, against one or two small files on the corpus.
- **Oracles are author-written**, as on the corpus, because Ibis has one test file with two test
  methods in 91k LOC. The self-authored-oracle threat of §4.8.2 applies here too.
