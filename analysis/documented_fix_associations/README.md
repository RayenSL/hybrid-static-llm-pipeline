# Documented fix-labelled edit study

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

This exploratory follow-up uses the three repository cohorts from the corrected maintenance-association analysis. It asks whether a production file containing a finding at an annual scan receives a fix-labelled modification in the following 365 days. The unit of analysis is a file at a snapshot; the outcome does not establish a defect in the flagged declaration.

Read the [protocol](PROTOCOL.md) before the [results report](results/v1.0/REPORT.md). The report distinguishes two source-checked class-level bug fixes from the automated file-level comparisons. The publication figure is available as [PDF](results/v1.0/adjusted-documented-fix-probability.pdf) and [PNG](results/v1.0/adjusted-documented-fix-probability.png). Optional thesis prose is in [LaTeX](results/v1.0/thesis-optional.tex).

From the repository root, prepare the checksum-pinned statistics environment as described in `analysis/maintenance_associations/prepare_statistics_runtime.py`, then run:

```sh
python3 analysis/documented_fix_associations/run.py \
  --packages /path/to/pinned-statistics-directory \
  --output /path/to/fresh-output-directory
```

The run refuses to overwrite existing results. `results/v1.0/provenance.json` records input and source identities; `results/v1.0/SHA256SUMS.json` seals the canonical analysis outputs. `results/v1.0/PUBLICATION_SHA256SUMS.json` seals the protocol, scripts, report, diagnostics, figure and optional thesis text. The checked replay matched all 11 canonical outputs byte for byte.
