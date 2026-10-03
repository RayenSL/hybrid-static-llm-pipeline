# Method-level fix-overlap follow-up

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

This [exploratory study](PROTOCOL.md) compares Long Methods with similar-sized unflagged methods in the same Jenkins or Tomcat production file. Its outcome is a subsequent issue-linked, fix-labelled edit inside the method body. Read the [results report](results/v0.1/REPORT.md) before using the estimates: the Tomcat association weakens when residual method-size imbalance is addressed.

The main run reads sealed annual syntax scans, the corrected file cohort, the prior candidate-fix ledger, and archived Git blobs. Restore the checksum-pinned Java parser wheels in `analysis/multilanguage_evolution/detectors/linux-wheel-lock.json` and the statistics runtime in `analysis/maintenance_associations/prepare_statistics_runtime.py`. Then, from the repository root, run:

```sh
PYTHONPATH=/path/to/pinned-parser-packages python3.12 analysis/method_fix_overlap/run.py \
  --parser-packages /path/to/pinned-parser-packages \
  --statistics-packages /path/to/pinned-statistics-packages \
  --output /path/to/fresh-output-directory
```

Use `--preflight` to produce a source-availability and exact missing-blob inventory before the full run. The analysis does not silently obtain absent blobs. The [pre-restoration audit](results/feasibility-v0.1/availability.json) and [full results](results/v0.1/REPORT.md) distinguish source availability from the scientific outcome.

If the preflight lists missing blobs, restore exactly the listed object IDs from the configured origin in batches, separately for Jenkins and Tomcat. The initial inventory is retained at `results/feasibility-v0.1/missing-blobs.csv`. For example, create a text file containing the second CSV column for one repository, one hash per line, then run `git --git-dir=tmp/maintenance-associations/git/<repository> -c gc.auto=0 -c fetch.negotiationAlgorithm=noop fetch origin --no-tags --no-write-fetch-head --no-auto-gc --stdin < <hash-list>`. Re-run preflight and require every candidate event to have both blobs locally before fitting. A fresh full replay matched all eight canonical outputs byte for byte.
