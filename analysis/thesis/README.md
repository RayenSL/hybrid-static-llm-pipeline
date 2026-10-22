# Final thesis output inventory

Reference: *LLM Powered Static Analysis for Anti-Pattern Repair and Maintenance*,
22 October 2026, 124 PDF pages, supplied as
`Static_Analysis_and_LLMs_for_Verified_Anti_Pattern_Repair.pdf`.
The reference fingerprint and restored input provenance are in
[data/provenance.json](data/provenance.json).

```bash
bash run_experiment.sh --out output/thesis-reproduction
bash run_experiment.sh --stage tables --out output/table-check
bash run_experiment.sh --stage figures --out output/figure-check
bash run_experiment.sh --study appendix-b --stage figures --out output/appendix-check
```

| Final thesis item | Source / generator |
|---|---|
| Figure 4.1, pipeline and experimental design | `architecture.py`, migrated from the final architecture-overview source |
| Figure 5.4, maintenance intervention effects | `maintenance_figures.py`, `data/maintenance_aggregates.json` |
| Figure C.1, starting-state comparisons | Same generator and checked aggregates |
| Figures B.1–B.2, annual counts and prevalence | `../multilanguage_evolution/plot_three_rule_trajectories.py`, `data/evolution/` |
| Figure B.3, God Class change-count ratios | `../god_class_change_count_thesis/render.py`, `data/god-class/models.csv` |
| Figure B.4, change categories | `../god_class_change_categories/combined_fix/render.py`, sealed counts in `data/categories/` |
| Tables 5.4–5.6 and C.2 | `tables.py`, retained factorial attempts, quality scores and paired contrasts |
| Tables 5.8 and C.3 | `tables.py`, retained corpus context summary |
| Table 5.9 | `tables.py`, reported industrial context aggregates; see limitation below |
| Tables 5.10, 5.12–5.13 and C.4–C.5 | `tables.py`, checked maintenance aggregate export |
| Tables 5.7 and 5.11 | `tables.py`, retained qualitative evidence |

Figure 1.1 and Figure 4.2 are manually authored conceptual diagrams. Figures 5.1–5.3
and 5.5 are typeset source excerpts; their public source excerpts, checks and provenance
remain in `data/qualitative/`. Conceptual, design, literature and prompt tables are authored
text, not Python-generated empirical results. Their LaTeX is outside the code repository.

`tables.py` exports 14 quantitative CSV tables with source hashes. Estimates in the paired
factorial CSV retain proportion units; multiply by 100 for the thesis's percentage points.
The maintenance plots derive their CSVs directly from checked aggregate reports.
`export_maintenance.py` can refresh the anonymous export from authorised private reports.
It does not run models or export industrial source code.

**Industrial context:** `data/industrial_context_reported.csv` is a transcription of final
Table 5.9, not an independent recomputation from private records. Its denominator is 27
assignments at each level. Use `tables.py --industrial-summary <summary.json>` with the
output of `context_ladder_industrial_analysis.py` to substitute recomputed values.
The wrapper exposes that analysis as `--study context-industrial --stage analyse`.

The checked aggregates retain the original source-report hashes. They do not imply that
private raw inputs are included. Regeneration of public outputs uses installed analysis
libraries; the frozen studies' runtime manifests identify their original environments.
