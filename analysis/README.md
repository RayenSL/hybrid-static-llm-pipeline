# Analysis and reproduction

The supported evidence is the **22 October 2026 thesis**. Its final inventory and input
provenance are in [thesis/README.md](thesis/README.md). Use the root
[`run_experiment.sh`](../run_experiment.sh) for all supported studies; the root README
documents native arguments, stage selection, requirements and model configuration.

```bash
python -m pip install -r analysis/requirements.txt
bash run_experiment.sh --list
bash run_experiment.sh --out output/thesis-reproduction
python -m unittest discover -s analysis/tests -v
```

`run_experiment.py` plans and executes the selected study. Dry runs require only Python's
standard library and do not create outputs, check credentials or launch model calls.
Each repair population and maintenance model retains its own denominator.

| Evidence | Retained analysis |
|---|---|
| Factorial outcomes and paired effects | `factorial_test_feedback_analysis.py`, `factorial_glmm.py`, `thesis/tables.py` |
| Corpus context outcomes | `context_ladder_analysis.py`, `matched_statistics.py` |
| Industrial context outcomes | `context_ladder_industrial_analysis.py` |
| Historical replay | `maintenance_efficiency/reaccrual/replay_analyze.py`, recurrence and sensitivity helpers |
| Corpus durability | `maintenance_efficiency/reaccrual/stratum_b_analyze.py`, `introduced_findings.py` |
| Controlled maintenance and replication | `maintenance_efficiency/reaccrual/v04_analyze.py` |
| Introduction-point intervention | `maintenance_efficiency/reaccrual/v05_analyze.py` |
| Final maintenance plots and tables | `thesis/maintenance_figures.py`, `thesis/tables.py`, `thesis/export_maintenance.py` |
| Annual evolution, Figures B.1–B.2 | `multilanguage_evolution/plot_three_rule_trajectories.py` |
| God Class change counts, Figure B.3 | `god_class_change_count_thesis/render.py` |
| Change categories, Figure B.4 | `god_class_change_categories/run_v1_1.py`, `god_class_change_categories/combined_fix/render.py` |

The final Appendix B CSVs and category-input seal are retained under `thesis/data/`.
Their original paths and hashes are recorded in `thesis/data/provenance.json`.
Rebuilding them from raw history still requires the source archives and runtimes in
[multilanguage_evolution](multilanguage_evolution/README.md), the corrected cohorts in
[maintenance_associations](maintenance_associations/README.md), and the first-parent
histories/file-event databases used by [change categories](god_class_change_categories/README.md).
Those upstream analysis and validation tools remain as reproduction dependencies.

The old factorial/context plots, plotting variants, coverage plot and redetection figure,
plus the independent Json.NET, documented-fix, method-overlap and mechanism table studies,
are absent from the final thesis and their generators have been retired. Current factorial
and context results are tables. Historical study documentation and immutable campaign
records may still mention the retired outputs; those records describe earlier work.

Generated outputs belong in ignored output directories. LaTeX source and runbooks are
removed. Source snapshots, public golden oracles, protocol freezes, tests and required
reproduction data remain. Industrial raw records and model credentials stay external;
only their checked aggregate export is needed for offline thesis rendering.
