# God Class count-ratio thesis insert

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

Use `results/v1.0/thesis-god-class-count.tex` in place of the mixed-rule `analysis/maintenance_associations/results/final-automated-analysis-v0.7/thesis-results.tex`. The earlier file and its generator remain unchanged because they belong to the sealed historical analysis. The new insert reports only the God Class adjusted mean change-count ratios. Copy `results/v1.0/god-class-adjusted-change-count.pdf` to the Overleaf `figures/` directory referenced by the LaTeX.

The source is the sealed `models.csv` from the final automated change-association analysis. Run from the repository root:

```bash
python3 analysis/god_class_change_count_thesis/render.py \
  --packages /tmp/bugfix-statistics \
  --output /tmp/god-class-count-replay
```

The script refuses to overwrite an existing non-empty directory. `provenance.json` records hashes of the input table and script; `SHA256SUMS.json` records the generated files. The PDF and LaTeX were regenerated in a fresh directory and matched the saved hashes exactly.

The count ratio concerns recorded file-change frequency over 365 days. It is not a measure of time spent, defect frequency or causal impact. Categorising the underlying changes into corrective, feature, security and other work requires a separate, validated commit/issue-linkage study; this insert does not assign such labels.
