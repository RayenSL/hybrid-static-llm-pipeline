# HybridLens

A hybrid static + LLM pipeline for analysing .NET codebases. It detects anti-patterns (god classes, long methods, obsolete API usage) using Roslyn static analysis, then grounds a configurable LLM to generate explanations and remediations for each finding.

## Solution structure

```
src/
├── HybridLens.Core             # Domain models and interfaces — no external dependencies
├── HybridLens.StaticAnalysis   # Roslyn workspace loader and anti-pattern detectors
├── HybridLens.ContextBuilder   # Assembles grounded prompts from findings
├── HybridLens.LLM              # LLM provider adapters (Claude, OpenAI, etc.)
├── HybridLens.Pipeline         # Orchestrates the full analysis flow
├── HybridLens.CLI              # Entry point — argument parsing, DI, config
└── HybridLens.Tests            # Unit and integration tests
```

See [pipeline modules and experimental invariants](src/HybridLens.Pipeline/README.md) for the execution boundaries and extension points.

## Research evidence

The code and retained data support the 22 October 2026 thesis. The
[figure and table inventory](analysis/thesis/README.md) maps its final outputs to
source code and records the PDF fingerprint. Experiment records, source snapshots,
oracles, frozen protocols and required analysis inputs are retained.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download)

## Build

Build the entire solution:

```bash
dotnet build src/HybridLens.slnx
```

Build a specific project:

```bash
dotnet build src/HybridLens.CLI
```

## Run

All thesis studies use **`run_experiment.sh`**. It resolves the repository root, so it
also works when invoked from another directory. Set `PYTHON` to select an interpreter.
Install the analysis dependencies first:

```bash
python -m pip install -r analysis/requirements.txt
bash run_experiment.sh --help
bash run_experiment.sh --list
bash run_experiment.sh --dry-run
bash run_experiment.sh --out output/thesis-reproduction
```

The default study, `thesis`, regenerates the final quantitative tables and Python-generated
figures from retained evidence. It makes no model calls and needs no .NET SDK or credentials.
Outputs go to a fresh timestamped directory under `output/` unless `--out` or `OUT` is set.
Existing table/model output directories are rejected to protect prior results.
Use `--stage tables`, `--stage figures`, or `--stage appendix-b` to run one part;
`--from figures` runs that part and the following parts. `--dry-run` prints commands
without checking external inputs or creating output directories.

### Initial repair and context campaigns

```bash
CORPUS=/path/to/Corpus.sln bash run_experiment.sh --study factorial --out experiments/my-run
bash run_experiment.sh --study factorial --out experiments/my-run --stage campaign
bash run_experiment.sh --study factorial --out experiments/my-run --from oracle
CORPUS=/path/to/Corpus.sln bash run_experiment.sh --study context-corpus --out experiments/my-context
```

| Study | Ordered stages |
|---|---|
| `factorial` | baseline, tests, manifest, campaign, oracle, quality, analyse |
| `context-corpus` | baseline, manifest, campaign, oracle, quality, analyse |
| `context-industrial` | baseline, manifest, campaign, oracle, quality, analyse |

`baseline` runs static analysis. `tests` attempts one diagnosis-blind test-generation
workflow per target (planning, implementation and at most a compile correction).
`manifest` freezes the assignments. `campaign` executes repairs and supports the
underlying runner's ledger-based resume. Private evaluation checks that every frozen
assignment has completed. `quality` measures the sealed sources. `analyse` actually
executes summaries and statistics; the factorial also exports its final tables.
Detector and private-oracle results never feed back into initial repair calls.

Campaigns require .NET 10, the matching corpus and configured models in
`src/HybridLens.CLI/appsettings.local.json`. Parameters include `MODEL` (default
`gpt-5.6-sol`), `RUNS` (3), `BUDGET` (6), `SEED` (503999552),
`BUILD_TIMEOUT` (180), `MAX_INPUT_TOKENS` (120000), `CLI`, and `DOTNET`.
Use one explicit output path when resuming. Fresh executions may differ from the sealed
results because model responses and environments can change. The old `MAX_TARGETS`
setting did not restrict the manifest and is now rejected; a bounded pilot needs an
explicitly filtered baseline before manifest creation.

The industrial context study additionally requires `INDUSTRIAL_TARGET`, `ADMITTED`,
`HARNESS` and `GOLDEN`. Its external evaluator uses `--no-restore`, preserves `obj`,
and passes `ProductRoot={WORKING_ROOT}` to the harness. Restore the industrial
solution's dependencies before running. Its population stays separate from the corpus.

### Maintenance studies

These studies retain their native arguments, freezes and resume rules. Pass native
options **after `--`**; use native `--out` there rather than the wrapper's output flag.
Select a single stage because preparation, execution and analysis consume different inputs.

| Study | Evidence | Stages |
|---|---|---|
| `replay` | Industrial historical replay, RQ3 | prepare, freeze, campaign, analyse, recurrence, sensitivity |
| `durability` | Cumulative corpus maintenance, RQ3 | prepare, freeze, campaign, analyse, introductions |
| `interventions` | Controlled maintenance, RQ4 | freeze, campaign, analyse |
| `introduction` | Industrial introduction-point intervention, RQ4 | prepare, freeze, campaign, analyse |
| `replication` | Second-model controlled maintenance, RQ4 | freeze, campaign, analyse |
| `maintenance-export` | Anonymous aggregate export from private reports | analyse |

```bash
bash run_experiment.sh --study replay --stage prepare -- --help
bash run_experiment.sh --study durability --stage campaign -- --help
bash run_experiment.sh --study interventions --stage freeze -- --packets /path/to/packets --write-freeze /path/to/freeze.json
bash run_experiment.sh --study interventions --stage campaign -- --packets /path/to/packets --out /path/to/run --provider live --freeze /path/to/freeze.json
bash run_experiment.sh --study interventions --stage analyse -- --run /path/to/run --out /path/to/report.json
bash run_experiment.sh --study introduction --stage prepare -- --help
bash run_experiment.sh --study replication --stage campaign -- --help
bash run_experiment.sh --study maintenance-export -- --private-root /path/to/reaccrual --out /path/to/maintenance_aggregates.json
```

The replication profile selects the recorded `claude-opus-5-5` deployment, Messages
API, temperature 1 and v0.6 protocol. `--model-key` can select the corresponding local
configuration entry. Freeze and execute with the same options. Maintenance defaults
are enforced by the underlying protocols and runners; no wrapper stage selects a live
provider on the user's behalf. Private sources, matching packets, admitted starting
states and oracles are needed for execution. Retained anonymous aggregates suffice for
thesis output regeneration.

### Appendix B and direct CLI use

```bash
bash run_experiment.sh --study appendix-b --stage figures --out output/evolution
bash run_experiment.sh --study appendix-b --stage scan -- --help
bash run_experiment.sh --study appendix-b --stage models -- --help
bash run_experiment.sh --study appendix-b --stage categories -- --help
```

Rendering uses retained final inputs. Rebuilding those inputs requires upstream source
archives, detector runtimes and corrected cohorts described in
[analysis/README.md](analysis/README.md). Native inputs and output flags follow `--`.

The CLI remains available for individual instrumentation operations:

```bash
dotnet run --project src/HybridLens.CLI -- analyse --target path/to/Solution.sln --dry-run --severity Warning --format json --output baseline.jsonl
dotnet run --project src/HybridLens.CLI -- --help
```

## Configuration

Configuration is loaded in the following order (later sources override earlier ones):

1. `src/HybridLens.CLI/appsettings.json` — committed defaults
2. `appsettings.local.json` (next to the binary) — local overrides, git-ignored

### Full config reference

```json
{
  "Detectors": {
    "GodClass": {
      "AtfdFew": 4,
      "WmcVeryHigh": 47,
      "TccThreshold": 0.3333
    },
    "LongMethod": {
      "MaxCyclomaticComplexity": 10,
      "MaxLinesOfCode": 50
    },
    "ObsoleteApi": {
      "DeprecatedNamespacePrefixes": []
    }
  },
  "Context": {
    "Strategy": "PerFinding",
    "Level": "Structural",
    "TokenBudget": 2000,
    "SnippetContextLines": 10,
    "Metadata": {}
  },
  "Llm": {
    "Temperature": 0.2,
    "MaxTokens": 1024,
    "Models": {
      "gpt-5.6-sol":     { "Provider": "azure",  "Model": "gpt-5.6-sol", "BaseUrl": "https://<your>.openai.azure.com" },
      "DeepSeek-V4-Pro": { "Provider": "azure", "Model": "DeepSeek-V4-Pro", "BaseUrl": "https://<your>.openai.azure.com" }
    }
  }
}
```

#### Detector thresholds

| Key | Default | Description |
|---|---|---|
| `Detectors.GodClass.AtfdFew` | `4` | ATFD (Access to Foreign Data) bound — flagged when ATFD strictly exceeds this |
| `Detectors.GodClass.WmcVeryHigh` | `47` | WMC (Weighted Method Count) bound — flagged when WMC ≥ this |
| `Detectors.GodClass.TccThreshold` | `0.3333` | TCC (Tight Class Cohesion) bound — flagged when TCC < this (1/3). All three conditions must hold. |
| `Detectors.LongMethod.MaxCyclomaticComplexity` | `10` | Primary gate — method flagged when cyclomatic complexity exceeds this |
| `Detectors.LongMethod.MaxLinesOfCode` | `50` | Secondary — escalates an already-flagged method to Critical |
| `Detectors.ObsoleteApi.DeprecatedNamespacePrefixes` | `[]` | Additional namespace prefixes to flag beyond `[Obsolete]` |

#### Context strategy

| Value | Behaviour |
|---|---|
| `PerFinding` | One LLM request per finding |
| `PerFile` | Findings grouped by file into one request |
| `PerClass` | Findings grouped by class into one request |

#### LLM providers

| `Provider` value | Notes |
|---|---|
| `claude` | Anthropic models (e.g. `claude-opus-4-8`) — requires an `ApiKey` on the model entry or `Llm.ApiKey` |
| `azure` | Azure OpenAI (e.g. `gpt-5.6-sol`) — requires `BaseUrl` + `ApiKey` |

Set your API key in a local override file (never commit this):

```json
// appsettings.local.json
{
  "Llm": {
    "ApiKey": "your-api-key-here"
  }
}
```

## Test

```bash
dotnet test src/HybridLens.slnx
```

Run tests for a specific project:

```bash
dotnet test src/HybridLens.Tests
```
