# Multi-language evolution analysis

> Generated results, figures and publication manifests were removed from this checkout.
> Paths and historical results described below refer to outputs that must be regenerated
> or restored before downstream analysis. Source code, protocols and dependency locks remain.

This directory contains the cross-language study for Odoo, Jenkins and Apache Tomcat. The modular suite implements experimental Long Method, God Class and source-declared Obsolete API Usage detection for Python and Java. A complete observation means that the declared static-analysis model covered the reviewed source population; it does not imply perfect runtime binding or scientific admission. The existing .NET repair pipeline is unchanged.

Read `detectors/SEMANTIC_RULES.md` for the exact mappings and `results/THREE_RULE_ANALYSIS.md` for the latest completed campaign when present. Both the original syntax contract (0.1) and the three-rule contract (0.2) retain `admitted: false`.

## What is implemented

- `audit_history.py`: pins the endpoint at a declared UTC cutoff, records first-parent histories, root anomalies, annual selections and tracked-language inventories. Product age is not inferred from GitHub creation dates.
- `export_sources.py`: exports source-only archives for frozen commits, with SHA-256 manifests and safe reuse checks.
- `detectors/syntax_probe.py`: enumerates named function/method definitions, computes an experimental syntax-based complexity measure, and records errors and denominators for Python, Java, C and C++.
- `contracts/findings.schema.json`: the versioned interchange format.
- `ingest/validate.py`: rejects invalid structure, inconsistent findings/denominators, duplicate source/definition entries, unsafe paths and incorrect missing-data handling.
- `run_probes.py`: connects the language adapters to ingestion and produces coverage summaries.
- `detectors/java/SemanticScan.java`: compiler-backed God Class metrics and source-deprecation references.
- `detectors/python/semantic.py`: conservative Python source bindings, class metrics and explicit deprecation markers.
- `detectors/multi_rule.py`: the three-rule envelope; `ingest/validate_multi_rule.py` checks it.
- `run_three_rules.py`: frozen annual campaign and deterministic replay.
- `plot_three_rule_trajectories.py`: separate annual count/PLOC and rule-specific prevalence figures.
- `prepare_semantic_runtime.py`: rebuilds the Linux runtime from checksum locks.
- `tests/`: executable mapping, semantic and contract checks.

The adapter carries repository/commit identity, language, source hashes, symbol kind and byte/line spans for future repair adapters. Build, runtime and semantic statuses are explicit. No non-.NET patch generation or repair validation is implemented.

## Environment and commands

The tested environment is Windows x86_64, CPython 3.12 and Tree-sitter 0.25.2. Version 0.26.0 caused an access violation on historical Java input during initial feasibility work and is not the frozen runtime. Dependencies are pinned in `detectors/requirements.txt`; `detectors/wheel-manifest.json` records the archived Windows wheel hashes. Other operating systems need their own wheel manifest before claiming binary-identical environment reproduction.

From the repository root, install dependencies into an isolated environment and use that environment's Python. In the existing Windows/WSL workspace, the bundled Windows Python can instead load packages from the explicitly supplied `--packages` directory.

```bash
python analysis/multilanguage_evolution/audit_history.py --cache /path/to/bare-clones --output analysis/multilanguage_evolution/selection/histories --cutoff 2026-09-14T00:00:00+00:00
python analysis/multilanguage_evolution/export_sources.py --cache /path/to/bare-clones --output /path/to/archives --repositories odoo__odoo jenkinsci__jenkins apache__tomcat --all-years
python analysis/multilanguage_evolution/run_probes.py --sources /path/to/archives --output /path/to/probes --repository odoo__odoo --all-years --legacy-python-through 2017 --python3-from 2017
python -m unittest discover -s analysis/multilanguage_evolution/tests -v
```

The source-only tar files and full probe outputs are kept in ignored `tmp/multilanguage-evolution/`. They are audit inputs, not source installations. Nothing in a target archive is executed by the parser probes. Canonical JSON contains relative source paths and no extraction-directory identity.

## Interpretation and limitations

The initial production filters are provisional. They exclude common test/example/vendor directories and generated-file markers, but have not yet undergone a full repository-specific provenance review. Odoo's bundled `bin/reportlab/` is additionally excluded based on its ReportLab copyright header. This is documented in `selection/odoo-probe-scope.json`.

A complete syntax probe means that the selected parser produced no error/missing nodes in the filtered source. It does not establish that all production source is in scope, that runtime semantics are resolved, or that a native configuration has been preprocessed correctly. In particular, `.h` files are probed with the C grammar in this initial inventory; native language routing remains a validation requirement. C++ header syntax can therefore account for some C-probe failures. Findings in partial probes are diagnostic only; their prevalence is null.

The common experimental rule counts named definitions with bodies, including Java constructors, and does not charge nested callable bodies to their enclosing function. This differs from the existing C# implementation, which enumerates method declarations and traverses descendants. Consequently, these values must not be pooled with the earlier Json.NET results. The God Class and obsolete-API modules are described separately in `detectors/SEMANTIC_RULES.md`; their declared populations and best-effort binding semantics must accompany any reported trajectory.

`admitted` is always false in contract 0.1. Repository-specific scope review, language-mapping validation, current build/smoke checks and independent full-snapshot reproduction are required before publishing anti-pattern trajectories. A later admitted-measurement contract needs an explicit protocol/version change; do not switch this flag by editing outputs.

Historical Python routing uses the separate `detectors/legacy_python.py` module and returns the same contract through `syntax_probe.py`. See `selection/DECISIONS.md` for the source evidence behind the 2017 transition and `detectors/RULE_MAPPING.md` for the exact experimental semantics.

## Three-rule campaign on Linux

Use CPython 3.12, with `requests` available for the download bootstrap. Keep large runtimes and results on a filesystem with sufficient free space; the current shared drive ran out of space during initial setup. The source archives are still in the existing ignored workspace cache.

```bash
python3 analysis/multilanguage_evolution/prepare_semantic_runtime.py --root /tmp/evolution-runtime
```

The bootstrap verifies existing locks, restores the official CPython legacy grammar, downloads the pinned JDK and compiles the Java adapter. It writes `runtime-paths.json`. From the repository root:

```python
import json, subprocess
from pathlib import Path
p = json.loads(Path('/tmp/evolution-runtime/runtime-paths.json').read_text())
subprocess.run([
    p['parser_python'], 'analysis/multilanguage_evolution/run_three_rules.py',
    '--parser-python', p['parser_python'], '--parser-packages', p['parser_packages'],
    '--java', p['java'], '--java-classes', p['java_classes'],
    '--sources', 'tmp/multilanguage-evolution/annual-sources',
    '--output', '/tmp/evolution-campaign', '--all-years', '--replay',
], check=True)
```

Use a new output directory for a new campaign; existing result files are not overwritten. `--repository` can restrict a run to one of the three selected repository identifiers. Omitting `--all-years` runs the fixed endpoint only. The original archive exporter recreates the source archives from their pinned commits if necessary.

After all observations finish, run `publish_three_rules.py --results /tmp/evolution-campaign --bundle` with the pinned package directory on `PYTHONPATH`. This validates each report and replay seal, writes all 189 rule observations to CSV, and packages the raw evidence and relevant adapter sources into a deterministic compressed bundle. It does not promote partial observations into complete counts or replace the thesis subsection.

For the full tests, set `PYTHONPATH` to the pinned package directory, `EVOLUTION_TEST_JAVA` to the Java executable and `EVOLUTION_TEST_JAVA_CLASSES` to the compiled adapter directory, then run `python3 -m unittest discover -s analysis/multilanguage_evolution/tests -v`. Without the Java variables, compiler integration tests are explicitly skipped.

`results/three-rule-environment.json` records the interpreter build and operating-system identity. The bootstrap pins dependencies and grammar sources; matching a different CPython build may reproduce measurements while changing recorded runtime provenance. The current byte-for-byte claim is the tested within-environment replay, not an assertion of cross-platform binary identity.

For independent batches, `run_three_rules.py --labels 2020 2021` selects explicit labels from the frozen manifest. `assemble_three_rule_campaign.py --case-source REPOSITORY=DIRECTORY ... --output DIRECTORY` combines selected batches only when every scheduled snapshot is present, every replay is verified and duplicate labels have identical hashes. Select one Tomcat scope version explicitly; conflicting results are rejected rather than silently preferred.
