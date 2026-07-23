# Phase C runbook — generate the gpt-5.4 corpus dataset

Executable procedure for the full controlled-experiment dataset on the constructed corpus,
single frontier model **gpt-5.4** (Azure OpenAI), non-evaluated applier **DeepSeek-V4-Pro** (Azure).
Run from the repo root. Commands are `dotnet run`; file ops are PowerShell.

> Companion to [THESIS_RECONCILIATION.md](THESIS_RECONCILIATION.md). Phases A & B are done;
> this is Phase C (generation + verification), with Phases D–E sketched at the end.

---

## 0. Preconditions (do not skip)

1. **Config** — `src/HybridLens.CLI/appsettings.local.json` must define both models:
   ```json
   {
     "Llm": {
       "Models": {
         "gpt-5.4":          { "Provider": "azure",  "Model": "gpt-5.4", "BaseUrl": "https://<your>.openai.azure.com", "ApiKey": "<azure-key>" },
         "DeepSeek-V4-Pro":  { "Provider": "azure", "Model": "DeepSeek-V4-Pro", "BaseUrl": "https://<your>.openai.azure.com", "ApiKey": "<azure-key>" }
       }
     }
   }
   ```
   The applier is a non-evaluated model from a different family than the evaluated gpt-5.4 (here
   **DeepSeek-V4-Pro**, Azure). Both arms use your existing Azure config — no Anthropic key needed.

2. **Corpus** present and frozen at `Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln` (v1.0).

3. **Clean slate** — archive any old run traces so the new campaign is unambiguous:
   ```powershell
   if (Test-Path runs) { Move-Item runs runs-archive-$(Get-Date -Format yyyyMMdd-HHmmss) }
   ```

Set the corpus path once:
```powershell
$CORPUS = "Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln"
```

---

## 1. Hybrid generation — 360 records (30 instances × 4 context levels × 3 runs)

One command per context level (each writes its own `runs/<stamp>.jsonl`):

```powershell
foreach ($lvl in "minimal","structural","relational","full") {
  dotnet run --project src/HybridLens.CLI -- analyse `
      --target $CORPUS --model gpt-5.4 --context-level $lvl `
      --severity Warning --max-findings-per-type 10 --runs 3 `
      --format json --output "runs/_hybrid-$lvl.json"
}
```

- `--severity Warning` includes the OB and borderline-LM warnings (the 30 seeded = 12 critical + 18 warning).
- `--max-findings-per-type 10` pins to exactly the 30 seeded instances (10 per type).
- Expect each level to send **30 findings × 3 runs = 90** generations → **360** total.
- Exit code **1** is the findings-gate (normal), not an error.

---

## 2. Analyser-only baseline — 30 deterministic records

```powershell
dotnet run --project src/HybridLens.CLI -- analyse `
    --target $CORPUS --context-level analyser-only `
    --severity Warning --max-findings-per-type 10 `
    --format json --output "runs/_analyser.json"
```
No model loop, no LLM call; one record per instance. (`--runs` is ignored for the baseline.)

---

## 3. Agentic arm (autonomous detect-and-repair loop, prompt v2.0.0)

Derives the 30 known instances from any hybrid trace and runs an **autonomous loop** over each
unannotated whole file: the agent edits the source and invokes the compiler (its only tool),
observes the build, and revises, until it declares completion or the iteration budget is spent.
The agent's **final solution is scored for verified-repair in-runner** — there is no separate
applier step for this arm (§4.7.1).

```powershell
$hybrid = Get-ChildItem runs/*.jsonl | Select-Object -First 1
dotnet run --project src/HybridLens.CLI -- agentic `
    --from $hybrid.FullName --target $CORPUS --model gpt-5.4 --runs 3 --budget 6
```

By default the agent runs over the **files holding a seeded instance** (matches the thesis 3F
run-count, F = files spanning the 30 instances). **Recall** is measured over the 30 known instances;
**precision** over spurious detections on those files. Add `--sweep-corpus` to run the agent over
every `.cs` (~61 files, incl. the clean/distractor set) for fuller precision over non-instances.

> **Runtime warning.** Each trajectory is a multi-turn loop: up to `--budget` (6) `dotnet build`s of
> the corpus, plus the final re-measure. ~30 instance files × 3 runs × up to 6 builds ≈ several
> hundred builds — **expect a long run**. Each trajectory (turns + build results + final source) is
> frozen under `runs/<stamp>-agentic-trajectories/`. The frozen corpus is never mutated (temp copy).

---

## 3b. Grounded-iterative arm (the H1c contrast, §4.4.1 / §5.1.5)

Identical loop, iteration budget, and compiler-only tool as the agentic arm — but the opening prompt is
seeded with the analyser's **Structural finding block** for each instance (rendered by `ContextBuilder`),
so the arm is *relieved of detection* and **varies grounding alone**. Point `--from` at a **structural**
hybrid trace: that trace carries the detector metrics the grounding block needs.

```powershell
$structural = Get-ChildItem runs/*.jsonl | Select-Object -First 1   # a structural-level hybrid trace
dotnet run --project src/HybridLens.CLI -- grounded-iterative `
    --from $structural.FullName --target $CORPUS --model gpt-5.4 --runs 3 --budget 6
```

It writes **no detection rows** (it is handed the findings) and, per instance, **two** verified-repair
rows — a `final` and a `first_build` snapshot. Together with the agentic arm's two snapshots these fill
the **2×2 of grounding × control structure** (Table 5.7); **H1c** is grounded-vs-ungrounded at the
iterative snapshot (Table 5.8), and Table 5.9 adds the single-shot grounding contrast (hybrid vs the
agentic first build). Keep `--budget` **identical** to the agentic arm so the control structure is held
fixed — that is the whole point of the contrast.

---

## 4. Verified-repair (objective repair outcome — hybrid arm only)

Combine the hybrid traces into one file, then apply → build → re-measure. Analyser-only rows (no repair)
and the iterative-arm rows (agentic + grounded-iterative, each scored in its own runner) are skipped
automatically.

```powershell
Get-Content runs/*.jsonl | Set-Content runs/_all.jsonl
dotnet run --project src/HybridLens.CLI -- verify-repair `
    --from runs/_all.jsonl --target $CORPUS `
    --applier DeepSeek-V4-Pro --out runs/_verified.jsonl
```

> **Runtime warning.** This applies the ~360 hybrid repairs, each = 1 applier call + 1 `dotnet build`
> of the corpus + 1 re-measure. The builds dominate — **expect a long run (likely 1–3 h)**. There is
> no resume; run it in one sitting (overnight is fine). The frozen corpus is never mutated (temp copy).

---

## 5. Detector agreement and automated final analysis

- **Band agreement.** The analyzer-only run re-measures every instance with the real HybridLens detector. `analysis/band_agreement.py` compares those metrics with the frozen truth records and fails if any instance disagrees. This check runs at full scale and is skipped for partial pilots.
- **Final analysis.** Combine the normal generation and verification traces, then generate reports directly:

```powershell
Get-Content runs/*.jsonl | Set-Content runs/_evaluation.jsonl
python analysis/analyse_results.py --input runs/_evaluation.jsonl --output output
python analysis/architecture_figure.py --out-dir output/figures
```

The reports cover persisted failures, lexical quality-attribute alignment, agentic recall and spurious detections, apply/build/re-measure outcomes, whole-solution analyzer deltas, and characterization-test results. Missing optional instruments and uncertain records are reported without blocking output.

---

## Expected volumes & cost

| Item | Count |
|---|---|
| Hybrid generations (gpt-5.4) | 360 |
| Analyser-only records | 30 |
| Agentic trajectories (gpt-5.4) | ~3 × (#instance files ≈ 30) ≈ 90, each a multi-turn loop |
| Grounded-iterative trajectories (gpt-5.4) | ~90 more (same shape as agentic; the H1c arm) |
| Applier calls (DeepSeek-V4-Pro) | ~360 (hybrid only; both iterative arms need no applier) |
| `dotnet build`s | ~400+ during verify-repair (hybrid) + up to budget × trajectories × 2 iterative arms |

LLM spend is modest (gpt-5.4 on small files); **wall-clock is dominated by the builds** — both the
verify-repair pass and the agentic loop — not the API calls.

## Open decisions before running
- ~~Agentic file scope~~ — **RESOLVED (2026-06-30)**: default = instance-spanning files only
  (matches the thesis 3F run-count); add `--sweep-corpus` for fuller precision over clean/distractors. See §3.
- ~~Agentic verified-repair~~ — **RESOLVED**: the agent's final solution is scored in-runner (no
  separate applier, §4.7.1); `verify-repair` is hybrid-only.
- ~~Grounding-vs-iteration confound (H1b)~~ — **RESOLVED (2026-07-02)**: added the **grounded-iterative**
  arm (§3b) and the first-build snapshot decomposition, forming the §4.4.1 2×2. H1c isolates grounding at
  the iterative snapshot; the first_build snapshots isolate iteration within each arm. Keep the agentic and
  grounded-iterative `--budget` equal, or the 2×2 no longer holds the control structure fixed.
- **Verify-repair coverage** — this runbook verifies *all* hybrid generations (thesis §5.2.5). If
  runtime is prohibitive, you could sample, but log it (no silent caps).
