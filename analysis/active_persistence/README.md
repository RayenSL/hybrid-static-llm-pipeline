# Active-file anti-pattern persistence

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

The [v1.0 report](results/v1.0/REPORT.md), [PDF figure](results/v1.0/active-file-redetection.pdf), and [thesis-ready LaTeX](results/v1.0/thesis-extension.tex) extend the three-repository annual detector campaign from aggregate counts to adjacent-snapshot finding redetection. Read [PROTOCOL.md](PROTOCOL.md) before interpreting the results.

The principal measure is the fraction of unique path-and-symbol findings redetected at the next complete annual scan among findings in production source files whose content changed between scans. This is descriptive presence in changing files, not the lifetime, cost or repair of an anti-pattern. Five corrected Odoo observations supersede their original chronology-invalid scans. API non-redetection does not establish removal because complete annual unflagged reference inventories are unavailable.

From the repository root, run `python3 analysis/active_persistence/run.py --output <fresh-directory>` to reproduce canonical tables. The default output is `results/v1.0` and will not be overwritten. Use the configured document Python runtime with ReportLab to run `analysis/active_persistence/render.py --results <directory>` for the PDF. A separate replay reproduced all nine canonical tables and manifests byte for byte. The input, protocol, code and publication hashes are retained under `results/v1.0`.
