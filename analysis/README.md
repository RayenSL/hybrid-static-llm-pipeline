# HybridLens automated evaluation

This directory contains the analysis tools that operate on normal pipeline run traces. The evaluation path requires no interactive input.

## Flow

```text
static analysis
  → grounded LLM explanation and repair
  → apply/build/re-measure verification
  → automated quality reports
```

The agentic and grounded-iterative arms also emit verification rows directly from their first-build and final snapshots. All arms can therefore be analyzed from their persisted JSONL records.

## Tools

| Tool | Input | Purpose |
|---|---|---|
| `loader.py` + `compare.py` | Generation JSONL | Failure, token, latency, uniqueness, and run-variance summaries |
| `band_agreement.py` | Analyzer trace + frozen corpus truth records | Confirms detector metrics against mechanically maintained ground truth |
| `analyse_results.py` | Generation and verification JSONL | Produces automated detection, repair, alignment, and whole-solution quality tables |
| `thesis_figures.py` | Automated CSV tables | Produces architecture, repair, recall, and quality figures |
| `layer3_run.py` + `layer3_figure.py` | Characterization project + repaired sources | Measures behavioral preservation |

## Setup

```bash
cd analysis
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Generate reports

Pass one or more paths or glob patterns:

```bash
python analysis/analyse_results.py \
  --input runs/phase-c-evaluation-combined.jsonl \
  --output output
```

Additional verification traces can be supplied separately when useful:

```bash
python analysis/analyse_results.py \
  --input 'runs/20260708-*.jsonl' \
  --verified 'runs/*-verified.jsonl' \
  --output output
```

Records are de-duplicated by `run_id`. Missing optional instruments are skipped; failed or truncated generations remain in the summaries and do not prevent report generation.

## Automated outputs

`output/tables/` may contain:

| Output | Meaning |
|---|---|
| `run_overview.csv` | Generation, verification, failure, and distinct-instance counts |
| `generation_counts.csv` | Records by architecture, context, and anti-pattern |
| `generation_failures.csv` | Persisted failure categories by architecture and context |
| `quality_attribute_alignment.csv` | Lexical mention alignment against the fixed anti-pattern-to-quality mapping |
| `agentic_recall.csv` | Agentic recovery of statically known instances with Wilson intervals |
| `agentic_spurious_summary.csv` | Matched and spurious agentic detections |
| `verified_repair_by_architecture.csv` | Apply/build/re-measure outcome ladder and resolved rate |
| `verified_repair_by_context.csv` | Verified repair outcome by context level |
| `verified_repair_2x2.csv` | Grounding × control-structure cells |
| `verified_repair_2x2_contrasts.csv` | Paired automated contrasts and McNemar p-values |
| `quality_impact_by_architecture.csv` | Whole-solution detector and independent analyzer deltas |

No subjective score is inferred from these fields. Explanation text remains available in raw records for inspection, but acceptance and aggregate reporting are based only on deterministic or programmatically measured outcomes.

## Raw run-trace inspection

```bash
python analysis/compare.py runs/*.jsonl
python analysis/compare.py runs/*.jsonl --field parsed_suggested_fix --export-csv reports/
```

The loader reports parse failures and uncertainty signals rather than suppressing rows. Every function returns a tidy pandas `DataFrame` for further analysis.

## Schema

Each JSONL line is a `RunRecord` serialized with snake-case names. Important automated fields include:

- identity: `run_id`, `timestamp`, `run_number`, `architecture`
- finding: `anti_pattern_type`, `file_path`, `symbol_name`, `line`, `severity`, `metrics`
- generation: `context_level`, `model_name`, prompts, raw output, parsed fields, tokens, duration
- quality mapping: `expected_quality_attributes`, `llm_quality_attributes_mentioned`, `quality_attribute_alignment`
- verification: `repair_applicable`, `build_passed`, `remeasured_metrics`, `verified_repair_ladder`, `verified_repair_success`
- quality impact: `quality_delta`
- agentic trace: `matched_instance_id`, `is_spurious`, `agentic_iterations`, `agentic_snapshot`
- uncertainty/failure: `context_truncated`, `parse_status`, `error_status`, `error_message`
