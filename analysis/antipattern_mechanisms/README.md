# Detector-specific follow-ups

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

This directory contains three exploratory analyses of Odoo, Jenkins and Apache Tomcat. They use the corrected annual source scans and first-parent Git histories already prepared in this repository. Read [PROTOCOL.md](PROTOCOL.md) for the frozen questions, populations and outcome definitions, and [results/v1.0/REPORT.md](results/v1.0/REPORT.md) for the findings.

Run from the repository root. The scripts refuse to overwrite a non-empty output directory:

```bash
python3 analysis/antipattern_mechanisms/trace_definitions.py \
  --output /tmp/antipattern-transitions-replay

python3 analysis/antipattern_mechanisms/change_spread.py \
  --packages /tmp/bugfix-statistics \
  --output /tmp/antipattern-spread-replay
```

The first script reads `analysis/multilanguage_evolution/results/three-rule-evidence.tar.gz` and the corrected Odoo scans in `analysis/maintenance_associations/results/calendar-frontier-v0.2`. The second reads `analysis/maintenance_associations/results/final-automated-analysis-v0.7/analysis-input.csv.gz` and `tmp/maintenance-associations/file-events/*.sqlite`. Prepare the pinned statistics runtime and event databases as described in `analysis/maintenance_associations/README.md` if they are absent. Each output directory contains input and script hashes, detailed row-level data, summary tables and its own SHA-256 manifest. A fresh run can be checked against the saved manifest with `diff`.

The analyses are observational and automated. Their three outcomes have different units and should not be pooled into one anti-pattern effect estimate.
