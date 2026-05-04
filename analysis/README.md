# HybridLens — run-trace analysis

This folder contains the Python tooling for the thesis. Two separate concerns
live here:

| Tool | Input | Purpose |
|---|---|---|
| `loader.py` + `compare.py` | Raw run-traces (`runs/*.jsonl`) emitted by the C# pipeline | Quick sanity tables, run-to-run variance, cross-model agreement, parse failures |
| `score_runs.py` | Raw run-traces | Interactive scoring tool — produces `experiments.jsonl` |
| `analyse_results.py` | Curated, **scored** experiments file (`experiments.jsonl` / `.csv`) | Thesis-ready figures and CSV tables for the evaluation chapter |

End-to-end workflow:

```
C# pipeline       →  runs/*.jsonl        (raw outputs)
score_runs.py     →  experiments.jsonl   (scored — your dependent variables)
analyse_results.py → output/figures/, output/tables/
```

The split is intentional: the run-trace contains every raw API call, while
`experiments.jsonl` is the smaller, hand-prepared file with the dependent
variables (correctness, completeness, hallucination type, developer-study
ratings, …) that your thesis actually evaluates.

## Setup

```bash
cd analysis
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## A. Producing `experiments.jsonl` — `score_runs.py`

Walks through each raw run-trace record and prompts you (the rater) for the
dependent variables: true-positive flag, six Likert scores, hallucination type.

```bash
# Score everything in one pass
python score_runs.py --input ../src/runs/*.jsonl --output experiments.jsonl

# Stratified subsample (essential for a manageable workload — 800 runs is too many)
python score_runs.py --input ../src/runs/*.jsonl --output experiments.jsonl \
                     --sample 60 --seed 42

# Score only one slice of the experiment matrix
python score_runs.py --input ../src/runs/*.jsonl --output experiments.jsonl \
                     --filter-model gpt-5-mini --filter-context-level relational
```

Per row the tool shows: anti-pattern, file/line, model, context level,
parsed explanation, parsed suggested fix. You then enter:

| Field | Scale | Notes |
|---|---|---|
| `is_true_positive` | y/n | Was the static finding actually a real issue? |
| `explanation_correctness_score` | 1–5 | |
| `explanation_completeness_score` | 1–5 | |
| `explanation_specificity_score` | 1–5 | |
| `quality_attribute_alignment` | 1–5 | |
| `repair_correctness_score` | 1–5 | |
| `repair_actionability_score` | 1–5 | |
| `hallucination_type` | menu | none / fabricated_api / wrong_logic / irrelevant / contradictory / other |

Commands:

| Input | Effect |
|---|---|
| `<Enter>` | Accept default (where shown) |
| `skip` | Skip this row entirely (no record written) |
| `quit` | Save what's been scored so far and exit |

The tool is **resumable**: re-running with the same `--output` file skips
`run_id`s already present. Filters and `--sample` apply before the
already-scored skip, so you can continue exactly where you left off.

`success` and `parsing_failed` are derived automatically from the run record's
`error_status` and `parse_status` — you don't score those.

## B. Thesis evaluation — `analyse_results.py`

Operates on the curated experiments file (one row per scored LLM run).
Generates every figure and table the thesis needs.

```bash
python analyse_results.py --input experiments.jsonl --output output
python analyse_results.py --input experiments.csv   --output output
python analyse_results.py --input experiments.jsonl --output output --only-true-positives
```

Outputs (auto-created):

```
output/
  figures/
    context_explanation_quality.png
    context_hallucination_rate.png
    context_repair_actionability.png
    model_explanation_quality.png
    model_hallucination_rate.png
    model_repair_quality.png
    anti_pattern_explanation_quality.png
    anti_pattern_hallucination_rate.png
    developer_condition_comparison.png
    hallucination_type_distribution.png
    hallucination_rate_by_model.png
    hallucination_rate_by_context_level.png
    quality_alignment_by_model.png
    quality_alignment_by_context_level.png
    quality_alignment_by_anti_pattern.png
    attribute_coverage_by_model.png
    attribute_coverage_by_context_level.png
    attribute_coverage_by_anti_pattern.png
  tables/
    overview.csv
    runs_by_model.csv
    runs_by_anti_pattern.csv
    runs_by_context_level.csv
    summary_by_context_level.csv
    summary_by_model.csv
    summary_by_anti_pattern.csv
    summary_by_developer_condition.csv
    developer_wilcoxon.csv         (only when paired data is detected)
    hallucination_overall.csv
    hallucination_type_distribution.csv
    hallucination_by_model.csv
    hallucination_by_context_level.csv
    alignment_by_model.csv
    alignment_by_context_level.csv
    alignment_by_anti_pattern.csv
```

The alignment tables include two columns:

| Column | Definition |
|---|---|
| `alignment_rate` | Mean of `quality_attribute_alignment` (0/1) — fraction of runs where at least one expected ISO/IEC 25010 attribute was mentioned by the LLM |
| `attribute_coverage` | Mean of `\|expected ∩ mentioned\| / \|expected\|` — finer-grained: how much of the literature-expected set the LLM actually covers |

Robustness: any analysis whose required column is missing prints a warning and
is skipped — the script never crashes on a partial file. The `--only-true-positives`
flag restricts quality-score analyses to confirmed positives; the overview and
hallucination sections always cover the full dataset so failures stay visible.

If the developer study contains paired observations (same `instance_id` rated
under both `condition` values), a Wilcoxon signed-rank test is run per metric
and saved to `developer_wilcoxon.csv`.

## C. Raw run-trace analysis — `compare.py`

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
| `cross_model_agreement` | Per (finding × level × run): do different models converge? |
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
