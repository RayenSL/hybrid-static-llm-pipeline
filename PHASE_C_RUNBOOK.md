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

## 4. Verified-repair (objective repair outcome — hybrid arm only)

Combine the hybrid traces into one file, then apply → build → re-measure. Analyser-only rows
(no repair) and agentic rows (scored in their own runner) are skipped automatically.

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

## 5. (Phase D) Band agreement + corpus R1 review

- **Band agreement — DONE (2026-06-23).** The analyser-only run re-measured every instance with the
  real HybridLens detector. `HybridLensMeasure` diverged on GodClass ATFD/WMC and one LongMethod CC
  (10/30; detection unaffected — all 30 still trigger). Decision: HybridLens is authoritative. The corpus
  `measured_metrics` were re-derived via `hybrid-pipeline-corpus/tools/apply_hybridlens_metrics.py` and
  re-checked with `analysis/band_agreement.py` → **30/30**. Re-run those two if the detector changes.
- **R1 corpus review** — populate `verification.reviewer_r1` in each `ground-truth/records/*.json`
  (single-rater; reviewer_r2 dropped per the decision). Then re-tag/re-freeze if anything changed.

## 6. (Phase E) Rating + final analysis

```powershell
# 1. pick one run per cell, stratified blinded order
python analysis/select_rating_set.py --input "runs/*.jsonl" --output experiments_to_rate.jsonl --seed 42
# 2. rate the architecture-contrast subset under rubric v1.0 (R1 full; R2 on the IRR subset)
python analysis/score_runs.py --input experiments_to_rate.jsonl --output experiments.jsonl --rater R1
# 3. inter-rater reliability
python analysis/compare_raters.py --r1 experiments.jsonl --r2 experiments_R2.jsonl
# 4. thesis tables + figures, INCLUDING verified-repair (Tables 5.3 / 5.7).
#    --verified globs BOTH the hybrid verify-repair trace AND the agentic trace (the agent's
#    final solutions carry verified-repair rows too), so Table 5.3 covers all three arms.
Get-Content runs/_verified.jsonl, runs/*-agentic.jsonl | Set-Content runs/_verified_all.jsonl
python analysis/analyse_results.py --input experiments.jsonl --verified runs/_verified_all.jsonl --output output
```

---

## Expected volumes & cost

| Item | Count |
|---|---|
| Hybrid generations (gpt-5.4) | 360 |
| Analyser-only records | 30 |
| Agentic trajectories (gpt-5.4) | ~3 × (#instance files ≈ 30) ≈ 90, each a multi-turn loop |
| Applier calls (DeepSeek-V4-Pro) | ~360 (hybrid only; agentic needs no applier) |
| `dotnet build`s | ~400+ during verify-repair (hybrid) + up to budget×agentic-trajectories (agentic loop) |

LLM spend is modest (gpt-5.4 on small files); **wall-clock is dominated by the builds** — both the
verify-repair pass and the agentic loop — not the API calls.

## Open decisions before running
- ~~Agentic file scope~~ — **RESOLVED (2026-06-30)**: default = instance-spanning files only
  (matches the thesis 3F run-count); add `--sweep-corpus` for fuller precision over clean/distractors. See §3.
- ~~Agentic verified-repair~~ — **RESOLVED**: the agent's final solution is scored in-runner (no
  separate applier, §4.7.1); `verify-repair` is hybrid-only.
- **Verify-repair coverage** — this runbook verifies *all* hybrid generations (thesis §5.2.5). If
  runtime is prohibitive, you could sample, but log it (no silent caps).
