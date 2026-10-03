# Reproducible Json.NET evolution study

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

This directory implements protocol 1.0.0 for a descriptive study of aggregate anti-pattern prevalence in Json.NET. The current evidence is a five-snapshot compatibility and reproducibility pilot. It deliberately gates, but does not yet run, the 70-unique-snapshot quarterly campaign.

`protocol.json` is authoritative. `study.py` selects commits from the pinned endpoint's first-parent history using UTC committer timestamps, creates byte-identical Git archives, captures compiler inputs from each original project, runs the unchanged HybridLens detectors, and retains denominators with raw findings. Every scan must compile without errors. A valid zero is distinct from failure.

The scanner is isolated under `Scanner/`. At run time, the script copies the detector and supporting source from this working tree, records every source hash, restores Roslyn 4.13.0 from a public-only NuGet configuration in locked mode, and bundles .NET runtime 10.0.11. Historical framework references are retained by content hash. The two replicas come from separate archive extractions. Offline replay reads only the frozen scanner, source blobs, references, compiler arguments, and protocol.

## Run

From WSL, first freeze the history and five source archives:

```bash
python3 analysis/jsonnet_evolution/study.py prepare \
  --git-cache /tmp/jsonnet-jsonnet.git \
  --archives tmp/jsonnet-evolution/archives
```

On this Windows/WSL environment, execute the pilot with Windows Python so all paths passed to MSBuild are native Windows paths:

```bash
WINPY='/mnt/c/Users/RayenSyal/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
"$WINPY" analysis/jsonnet_evolution/study.py pilot \
  --archives Z:/GitHub/hybrid-static-llm-pipeline/tmp/jsonnet-evolution/archives \
  --output Z:/GitHub/hybrid-static-llm-pipeline/tmp/jsonnet-evolution/run-1 \
  --dotnet 'C:/Program Files/dotnet/dotnet.exe' \
  --msbuild 'C:/Program Files/Microsoft Visual Studio/18/Professional/MSBuild/Current/Bin/MSBuild.exe'
```

The output directory is immutable: a run refuses to overwrite it. Verify its seal and replay without Git, MSBuild, an SDK, NuGet, or network access:

```bash
"$WINPY" analysis/jsonnet_evolution/study.py verify Z:/GitHub/hybrid-static-llm-pipeline/tmp/jsonnet-evolution/run-1
"$WINPY" analysis/jsonnet_evolution/study.py replay Z:/GitHub/hybrid-static-llm-pipeline/tmp/jsonnet-evolution/run-1
```

The pilot requires SDK 10.0.203, runtime 10.0.11, Visual Studio MSBuild 18.5, and access to nuget.org only while freezing the scanner and reference packages. Replay has none of those external requirements because the runtime and all analysis inputs are bundled. Reference-assembly redistribution terms should be checked before publishing a full bundle; the checksums and package URLs can be published independently.

## Interpretation

The unit for God Class is a class declaration, including each partial declaration separately. The unit for Long Method is a method declaration. Obsolete API findings count distinct referenced symbols per eligible file under the existing detector; the normalized measure is the share of eligible files with one or more findings. Framework transitions are reported because they can change conditional source and available APIs.

Aggregate trajectories support claims about prevalence at sampled revisions. They cannot show that the same finding persisted, that maintainers failed to resolve a particular problem, or that anti-pattern changes caused quality changes. Those claims require finding lineage or a repair study.

## Pilot figure

Generate the publication-ready pilot timeline with `python3 analysis/jsonnet_evolution/plot_pilot.py`. The canonical SVG, a PNG preview, exact plotted data, and interpretation notes are under `figures/`.

The denser annual series is governed by `protocol-annual-1.1.0.json`. Its twenty reproduced measurements and comparison evidence are in `annual_results/`; regenerate the vector chart with `python3 analysis/jsonnet_evolution/plot_annual.py`.

## Three-system annual comparison

The same detector thresholds, denominator definitions, annual selection rule, exclusions, and A/B/offline reproduction gate are applied to OpenRA and nopCommerce through their repository-specific protocol adapters. The adapters identify the corresponding primary project and historical build dependencies; they do not edit target source. Compact evidence is in `openra_annual_results/` and `nopcommerce_annual_results/`.

```bash
python3 analysis/jsonnet_evolution/plot_comparison.py
python3 analysis/jsonnet_evolution/validate_comparison.py
```

See `COMPARATIVE_ANALYSIS.md` for coverage limitations and case-selection guidance. The comparison CSV retains every scheduled observation and leaves metrics blank when a revision is incomplete or fails reproduction.
