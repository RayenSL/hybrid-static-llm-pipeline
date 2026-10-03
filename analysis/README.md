# Analysis and reproducibility

This directory contains the analyses supporting *Static Analysis and LLMs for Verified
Anti-Pattern Repair* (3 October 2026). The revised thesis reports three separate repair
populations and an exploratory evolution study in Appendix B. Keep their denominators
and statistical interpretations separate.

## Generated outputs

This checkout keeps analysis code, tests, protocols, dependency locks and frozen
input-selection records. Generated `results/`, `*_results/`, `figures/`, logs, caches
and their top-level publication hash manifests have been removed and are ignored.
Result paths below describe expected outputs, not files shipped in this checkout.

Some analyses consume earlier stages' results, source archives or file-event databases.
Regenerate or restore those inputs before running downstream summaries and renderers.
The study READMEs retain the commands and historical interpretation; their result links
refer to generated artifacts. The cleanup recovery archives are stored outside this repository.
Raw repair campaigns under `experiments/` are unchanged by this cleanup.

## Setup

Run commands from the repository root with Python 3.12 or later:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r analysis/requirements.txt
python -m unittest discover -s analysis/tests -v
```

These requirements cover the general analysis tools. The Appendix B studies retain
separate checksum-pinned parser and statistics runtimes; follow their own READMEs.

## Repair experiments in Chapters 4–6

| Evidence | Tools | Saved inputs/results |
|---|---|---|
| Confirmatory factorial: 26 targets, 624 assignments | `factorial_test_feedback_analysis.py`, `factorial_glmm.py`, `confirmatory_v2_figures.py` | `experiments/confirmatory-v2-gpt56-sol-20260812/` |
| Four-level corpus context comparison | `context_ladder_analysis.py` | `experiments/context-ladder-corpus-v2-20260816/` |
| Industrial context comparison | `context_ladder_industrial_analysis.py` | See [industrial runbook](../RUNBOOK-context-ladder-industrial.md); restricted source and harness are required |
| Context comparison figures | `context_ladder_thesis_package.py` | Separate corpus and industrial summary files |
| System architecture | `architecture_figure.py` | Diagram source; verified by `tests/test_architecture_figure.py` |
| Illustrative repairs | Source excerpts and remeasurement records | [Qualitative repair evidence](../docs/qualitative-repairs/README.md) |

The factorial analysis averages repetitions within each target before computing paired
contrasts. The industrial analysis is descriptive. The corpus and industrial context
campaigns use direct editing; the older suggestion-plus-applier experiment is a separate
historical campaign.

Inspect the command-line interfaces before choosing fresh output directories:

```bash
python analysis/factorial_test_feedback_analysis.py --help
python analysis/factorial_glmm.py --help
python analysis/confirmatory_v2_figures.py --help
python analysis/context_ladder_analysis.py --help
python analysis/context_ladder_industrial_analysis.py --help
python analysis/context_ladder_thesis_package.py --help
```

Use [the corpus runbook](../RUNBOOK-context-ladder-corpus.md) and
[the industrial runbook](../RUNBOOK-context-ladder-industrial.md) for campaign-specific
inputs, frozen protocols and reproduction commands. `prepare_v2_run.py` prepares and
checks the confirmatory run; `chapter54_quality_rescore.py` performs offline quality
remeasurement. `extraction_vs_simplification.py` classifies archived repair diffs.
Do not overwrite sealed experiment results when checking a rerun.

## Appendix B

| Thesis evidence | Directory | Dependencies to retain |
|---|---|---|
| Annual counts and prevalence (Figures B.1–B.2) | [multilanguage_evolution](multilanguage_evolution/README.md) | Frozen source archives, detector contracts, scope rules and scan evidence |
| God Class change counts (Figure B.3) | [god_class_change_count_thesis](god_class_change_count_thesis/README.md) | [maintenance_associations](maintenance_associations/README.md) corrected cohorts and fitted models |
| Change categories (Figure B.4) | [god_class_change_categories](god_class_change_categories/README.md), including `combined_fix/` | Corrected cohorts, file-event databases and first-parent histories |
| Finding redetection (Figure B.5) | [active_persistence](active_persistence/README.md) | Annual scan evidence and corrected Odoo observations |

The maintenance-association scripts remain to regenerate the corrected cohorts and
models used by downstream studies. Publication renderers remain because they produce
the figures and accompanying LaTeX from those results.

The Json.NET evolution/repository-selection pilot and the mechanism, documented-fix
and method-overlap follow-ups retain their source code and protocols as well. These
exploratory tools are separate from the results reported in the revised thesis.

## Shared and historical utilities

`loader.py`, `compare.py` and `analyse_results.py` inspect normal pipeline JSONL traces.
`band_agreement.py` compares detector metrics with the frozen corpus truth records.
For example:

```bash
python analysis/analyse_results.py --input 'runs/*.jsonl' --output output
python analysis/compare.py 'runs/*.jsonl'
```

The legacy figure and packaging tools (`thesis_figures.py`, `sol_thesis_figures.py`,
`chapter54_sol_package.py`, `grounding_context_analysis.py`, `render_grounding_figure.py`,
`layer3_run.py`, `layer3_figure.py`, `metric_reduction_figure.py`,
`metric_trajectory_figure.py`, and `quality_impact_figure.py`) remain for their archived
campaigns or reusable measurements. Their historical figure numbers do not identify the
current thesis figures. Use `confirmatory_v2_figures.py` for the final factorial figures.

One-off chapter-restructuring and prose-integration scripts have been removed. Thesis
writing Markdown is separate from the retained protocols, source evidence and operational
documentation. Presentation slides and speaker notes live in [presentations](../presentations/).
