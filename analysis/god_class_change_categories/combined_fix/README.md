# Combined fix-labelled God Class figure

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

Use [results/v1.0/god-class-change-categories.pdf](results/v1.0/god-class-change-categories.pdf) as the thesis figure and [results/v1.0/thesis-insertion.tex](results/v1.0/thesis-insertion.tex) as its accompanying text. The [report](results/v1.0/REPORT.md) explains the adjusted ratios, file-event shares and limits. The [protocol](PROTOCOL.md) defines the combined category and the fixed comparison before fitting.

Reproduce from the repository root with the pinned statistics runtime:

```bash
python3 analysis/god_class_change_categories/combined_fix/render.py \
  --packages /tmp/bugfix-statistics \
  --output /tmp/god-class-combined-fix-replay
```

The script reads and verifies the sealed v1.1 comparison counts, reproduces the prior total-change ratios, then refits the combined and remaining categories. It refuses to overwrite a non-empty directory. Compare the fresh `SHA256SUMS.json` to the archived one; the PDF, PNG, LaTeX and tables matched exactly in the recorded replay.
