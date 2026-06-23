# HybridLens — run-trace analysis

This folder contains the Python tooling for the thesis. Tools by stage:

| Tool | Input | Purpose |
|---|---|---|
| `loader.py` + `compare.py` | Raw run-traces (`runs/*.jsonl`) | Quick sanity tables, run-to-run variance |
| `select_rating_set.py` | Raw run-traces | Uniform random draw of 1 run per cell + stratified order → `experiments_to_rate.jsonl` (§5.2.5, §B.2.2) |
| `score_runs.py` | `experiments_to_rate.jsonl` | Apply the rubric (Appendix B): 3-point ordinal × 8 dimensions, multi-label hallucination, mandatory rationales, blinded viewer |
| `compare_raters.py` | Two `experiments_*.jsonl` files | Cohen's weighted κ + Krippendorff's α for IRR (§B.8) |
| `analyse_results.py` | `experiments.jsonl` | Proportions per ordinal level, Wilson CIs, Cliff's δ, thesis-ready figures |

End-to-end workflow:

```
C# pipeline           →  runs/*.jsonl              (raw outputs)
select_rating_set.py  →  experiments_to_rate.jsonl (1 row per cell, stratified order)
score_runs.py --rater R1 → experiments.jsonl       (rated by primary rater)
score_runs.py --rater R2 → experiments_R2.jsonl    (rated by second rater, IRR subset)
compare_raters.py     →  IRR statistics (Cohen's κ)
analyse_results.py    →  output/figures/, output/tables/
```

## Setup

```bash
cd analysis
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## A. Selecting the rated subset — `select_rating_set.py`

Picks **one run per (instance × context × model) cell** by uniform random draw
with a recorded seed (§5.2.5), then re-orders the result so no two consecutive
outputs share the same instance, model, or context level (§B.2.2).

```bash
# Full primary rating set (390 rows from 1,110 raw runs at 30 instances)
python select_rating_set.py --input ../src/runs/*.jsonl \
                            --output experiments_to_rate.jsonl --seed 42

# IRR pilot subset (~10 outputs, balanced across context × anti-pattern)
python select_rating_set.py --input ../src/runs/*.jsonl \
                            --output experiments_pilot.jsonl --seed 42 --pilot

# IRR stratified subsample (~30% of primary set, stratified by
# anti-pattern × context × model, per §B.8.1)
python select_rating_set.py --irr-from experiments_to_rate.jsonl \
                            --output experiments_irr.jsonl \
                            --seed 42 --irr-fraction 0.30
```

Produces `experiments_to_rate.jsonl` plus a `.manifest.json` sidecar recording
the seed, the lot ID, and the counts per model / context / anti-pattern. The
manifest is what makes the selection reproducible — keep it under version control.

Each row of the output gets:
- `presentation_index` — 1..N order
- `blinding_lot` — short stable lot ID (so second-rater files reference the same lot)
- `selection_seed` — the seed used

## B. Scoring — `score_runs.py`

Applies the rubric defined in **Appendix B** of the thesis.

```bash
# Primary rater (default --viewer html opens a blinded browser tab)
python score_runs.py --input experiments_to_rate.jsonl \
                     --output experiments.jsonl --rater R1

# Second rater (IRR — points at a smaller subset file produced by select_rating_set.py)
python score_runs.py --input experiments_irr.jsonl \
                     --output experiments_R2.jsonl --rater R2

# Pure-console mode (no browser)
python score_runs.py --input experiments_to_rate.jsonl --rater R1 --viewer console
```

For each row the rater enters:

| Field | Scale | Notes |
|---|---|---|
| `explanation_correctness` | poor / adequate / good | §B.4.1 |
| `explanation_groundedness` | poor / adequate / good | §B.4.2 |
| `explanation_completeness` | poor / adequate / good | §B.4.3 |
| `explanation_clarity` | poor / adequate / good | §B.4.4 |
| `repair_correctness` | poor / adequate / good | §B.5.1 |
| `repair_completeness` | poor / adequate / good | §B.5.2 |
| `repair_actionability` | poor / adequate / good | §B.5.3 |
| `repair_semantic_risk` | poor / adequate / good | §B.5.4 — **reverse-coded**: Good = low risk |
| `hallucination_categories` | multi-select | §B.6 — any-of-7 + none |
| `attributes_correctly_aligned` | integer | §B.7.2 |
| `incorrectly_mentioned_attributes` | integer | §B.7.2 |

Input cheat-sheet:

| Input | Effect |
|---|---|
| `p` / `a` / `g` | Poor / Adequate / Good |
| `p?` / `a?` / `g?` | Same, but marked uncertain (rationale required, `*_uncertain` flag set) |
| `skip` | Skip the row entirely |
| `quit` | Save and exit |
| `<Enter>` | Accept the default (where one is shown) |

**Mandatory rationale** is required for any Poor or uncertain rating (§B.3.2).
The tool will not let you proceed without one. Append `?` to any rating
(`p?`, `a?`, `g?`) to mark it uncertain — this also triggers the rationale
prompt and sets the `*_uncertain` boolean on the record.

**Refusal detection** (§B.3.4): outputs matching common refusal phrases ("I cannot
help…", "I'm unable to…") are flagged. The tool pre-fills all dimensions as Poor
with rationale "refusal" and asks you to confirm. Type `override` to score manually.

**Blinded HTML viewer**: the rater never sees `context_level`, `model_name`,
`run_number`, or `prompt_version`. The browser tab shows only what §B.2.1 permits
(anti-pattern, severity, file:line, symbol, code snippet, parsed explanation /
quality impact / suggested fix, expected & mentioned attributes).

**Resume support**: re-running with the same `--output` and `--rater` skips
`run_id`s this rater has already scored. Switching `--rater` writes a new pass.

Each record carries the audit fields required by §B.10.1:
`rater_id`, `rubric_version` (`"1.0"`), `rated_at`, `rating_started_at`,
`rating_completed_at`, `rating_duration_seconds`, `blinding_lot`.

## C. Inter-rater reliability — `compare_raters.py`

Reports Cohen's weighted κ (linear weights) per ordinal dimension and binary κ
per hallucination category, with the Landis–Koch interpretation and the §B.8.2
acceptance threshold (κ ≥ 0.60).

```bash
python compare_raters.py --r1 experiments.jsonl --r2 experiments_R2.jsonl
python compare_raters.py --r1 experiments.jsonl --r2 experiments_R2.jsonl \
                        --output output/irr --threshold 0.60
```

Outputs:

```
output/irr/
  kappa_ordinal.csv          # κ + interpretation + accepted? per dimension
  kappa_hallucination.csv    # κ per hallucination category
  disagreements_<dim>.csv    # per-dim list of run_ids where R1 ≠ R2 (with both rationales)
```

If any dimension falls below the threshold, the script flags it as a §B.9
trigger ("invoke conflict resolution"). Persistent disagreements are not
averaged — see §B.9.1.

## D. Thesis evaluation — `analyse_results.py`

Operates on the rated experiments file (one row per rated LLM output).
Generates the descriptive tables and figures the thesis presents in §5.4.

```bash
python analyse_results.py --input experiments.jsonl --output output
```

What it computes (per Methodology §4.5–4.6 + Appendix B):

| Block | Output | What it answers |
|---|---|---|
| Overview | `overview.csv`, `n_by_*` | Sample sizes, rater counts, refusal count, rating-time stats |
| Ordinal proportions | `{dim}_by_{group}.csv` + stacked bar PNG | Poor/Adequate/Good proportion per cell, Wilson 95 % CIs, for each of 8 dimensions × {context_level, anti_pattern_type} |
| Hallucinations | `hallucination_overall.csv`, `hallucination_by_context.csv` | Per-category rate with Wilson CIs (multi-label) — RQ1.2 |
| Quality-attribute | `quality_alignment_by_anti_pattern.csv`, `alignment_rate_by_anti_pattern.csv` | Mean correctly-aligned + incorrect count per anti-pattern — RQ1.3 |
| H1 baseline | `h1_baseline_vs_hybrid_cliffs_delta.csv` | Paired Cliff's δ comparing `analyser_only` vs each hybrid level, per dimension |
| H2 long-format | `context_monotonicity_long.csv` | One row per (dim × context × ordinal level) with count + proportion + CIs — input file for the CLMM fitted in R |

Statistical primitives used internally:

| Primitive | Where |
|---|---|
| Wilson 95 % CI | Every proportion (binomial CI; respects 0 and 1) |
| Cliff's δ | H1 paired comparison (with Romano et al. thresholds: small 0.147 / medium 0.330 / large 0.474) |
| Holm–Bonferroni | Available as `holm_correct(pvals)` — applied where multiple p-values from the same family are reported |

Charts use a colour-blind safe traffic light: red for Poor, amber for Adequate,
green for Good. No seaborn.

### What deliberately isn't in this script

* **Cumulative-link mixed-effects models (CLMM)** — fitted in R using
  `ordinal::clmm`. The `context_monotonicity_long.csv` file is the input to
  that R workflow. Python's `statsmodels` lacks a robust ordinal mixed-effects
  implementation.

## E. Raw run-trace analysis — `compare.py`

```bash
# Single campaign
python compare.py ../runs/20260507-final.jsonl

# Multiple campaigns side-by-side (filename stem becomes the `campaign` column)
python compare.py ../runs/*.jsonl

# Use a different parsed field for similarity / uniqueness
python compare.py ../runs/*.jsonl --field parsed_suggested_fix

# Also dump every table as CSV
python compare.py ../runs/*.jsonl --export-csv ./reports/
```

The CLI prints the following standard tables in order:

| Table | What it answers |
|---|---|
| `summary` | Row count, # findings, # models, # context levels, error totals |
| `failure_rates` | % of (model × context-level) cells that errored — Req #8 |
| `error_breakdown` | Counts per `error_status` category (api / parse / empty / cancel / …) |
| `token_cost` | Mean & sum of input/output tokens + p95 latency per cell |
| `output_uniqueness` | Per (finding × model): does context level change the answer? |
| `run_variance` | Per (finding × model × level): pairwise similarity across runs — Req #5 |
| `parse_failures` | First 50 rows where structured-output parsing failed |

## Library usage (notebooks)

```python
import sys; sys.path.append("../analysis")
import loader

df = loader.load("../runs/*.jsonl")

loader.summary(df)
loader.failure_rates(df)
loader.run_variance(df, field="parsed_suggested_fix")
```

Every function returns a tidy DataFrame, so chaining with `.query(...)`,
`.merge(...)`, `seaborn.heatmap(...)`, etc. is straightforward.

## Suggested notebook layout for the thesis

```
analysis/
  loader.py
  compare.py
  notebooks/
    00_load_and_overview.ipynb     ← imports loader, runs summary / failure_rates
    01_rq1_context_effect.ipynb    ← output_uniqueness + plots
    02_rq2_run_variance.ipynb      ← run_variance + boxplots
    03_rq3_cost_analysis.ipynb     ← token_cost charts
    04_failure_audit.ipynb         ← parse_failures + manual notes
```

## Schema reference

Each line in a run-trace JSONL file is one `RunRecord` from the C# code
(`HybridLens.Core.Models.RunRecord`). Fields are written in `snake_case`
for direct pandas/R consumption. Key columns:

| Column | Type | Notes |
|---|---|---|
| `run_id` | str | Globally unique per record (uuid) |
| `timestamp` | ISO-8601 | UTC |
| `run_number` | int | 1..N for repeated runs of the same condition |
| `anti_pattern_type` | str | `god_class` / `long_method` / `obsolete_api_usage` |
| `file_path`, `symbol_name`, `line` | — | Identifies the finding |
| `severity` | str | `critical` / `warning` / `info` |
| `context_level` | str | `minimal` / `structural` / `relational` / `full` |
| `model_name` | str | Key from `Llm.Models` config |
| `prompt_version` | str | e.g. `v1.0.0` — bumped whenever the prompt changes |
| `raw_system_prompt`, `raw_user_prompt` | str | Full audit trail (Req #2) |
| `raw_llm_output` | str \| null | Full model response or null on API failure |
| `input_tokens`, `output_tokens`, `duration_ms` | num \| null | |
| `parsed_explanation`, `parsed_quality_impact`, `parsed_suggested_fix`, `parsed_risks` | str \| null | Quality-impact and risks are filled when the prompt is upgraded past v1.0.0 |
| `parse_status` | str | `ok` / `failed` / `not_attempted` |
| `error_status` | str \| null | `api_failure` / `empty_response` / `parse_failure` / `token_limit_truncation` / `unsupported_file` / `context_extraction_failure` / `cancelled` / `unknown` |
| `error_message` | str \| null | Raw exception message |
| `campaign` | str | Added by `loader.load()` — filename stem of the source JSONL |
