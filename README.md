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

### Analyse a solution or project

Static analysis only, no model call. This is also how a campaign baseline is produced.

```bash
dotnet run --project src/HybridLens.CLI -- analyse --target path/to/Solution.sln --dry-run     --severity Warning --format json --output baseline.jsonl
```

`--target` accepts a `.sln` or a `.csproj`. Add `--config path/to/hybridlens.json` to override
detector thresholds. Drop `--dry-run` to send each finding to the configured models.

### The confirmatory experiment, end to end

```bash
bash run_experiment.sh                    # every stage, in protocol order
bash run_experiment.sh --dry-run          # print the commands, execute nothing
bash run_experiment.sh --stage campaign   # one stage
bash run_experiment.sh --from oracle      # that stage and everything after
bash run_experiment.sh --help
```

Six stages, in an order the protocol fixes rather than one chosen for convenience:

| stage | what it does | model calls |
|---|---|---|
| `baseline` | detector over the pristine solution | none |
| `tests` | one diagnosis-blind five-case characterisation suite per target | two per target, plus at most one compile-only correction |
| `manifest` | freezes the randomised assignment schedule | none |
| `campaign` | executes the assignments, sealing one final source each | one per assignment, or up to the budget when iterative |
| `oracle` | private Layer-3 behavioural measurement | none |
| `analyse` | summary, statistics, figures | none |

Two properties matter more than the stage list. Behavioural measurement happens only in `oracle`,
after every repair condition has terminated, so no repair can be tuned to the oracle that scores it.
And detector re-measurement and private results are withheld from every model call, so the only
feedback an iterative condition receives is the compiler and, where assigned, a visible test.

Environment overrides; the defaults reproduce the reported run.

```bash
MODEL=gpt-5.6-sol RUNS=3 BUDGET=6 SEED=503999552 CORPUS=path/to/Corpus.sln bash run_experiment.sh
```

A cheap orchestration pilot over one target and one repetition:

```bash
RUNS=1 MAX_TARGETS=1 bash run_experiment.sh
```

### Inspect a manifest before spending model calls

`--dry-run` validates the manifest, the target solution, the frozen baseline hash and every pristine
source hash, then prints the plan and stops.

```bash
dotnet run --project src/HybridLens.CLI -- factorial-campaign     --manifest <manifest>.json --out <campaign-dir> --dry-run
```

The campaign is crash-safe: an interrupted run resumes from its ledger and never repeats a committed
assignment. An incomplete trace must be quarantined before resuming, which the command enforces.

### Other experiments

These have their own denominators and are never pooled with the confirmatory factorial.

**Four-level context supplement** — Minimal, Structural, Relational and Full context through the
suggestion-plus-applier mechanism, where a non-evaluated applier materialises each recommendation
under a strict-literal contract.

```bash
dotnet run --project src/HybridLens.CLI -- grounding-campaign     --manifest <grounding-manifest>.json --out <campaign-dir> --preflight-only
```

The applier must be a different model from the evaluated one, so it never scores code it wrote
itself. Configure it alongside the evaluated model in `appsettings.local.json`.

**Iterative arms** — `agentic` is ungrounded and `grounded-iterative` differs from it only in that
the opening message carries the analyser's Structural finding. Both grant the compiler as the sole
external check and share the frozen build-attempt budget; keeping the budget equal is what holds the
control structure fixed between them.

```bash
dotnet run --project src/HybridLens.CLI -- agentic     --from <structural-trace>.jsonl --target path/to/Corpus.sln     --model gpt-5.6-sol --runs 3 --budget 6
```

By default the agent sees only files holding a target. `--sweep-corpus` widens it to every `.cs`
file so a detection on a clean file scores as spurious, which is what makes precision measurable
over known-clean code rather than within target files alone.

**Repair verification for the suggestion-plus-applier mechanism** — applies each recommendation
strict-literally, rebuilds, and re-measures the triggering condition, scoring the ladder
`unapplicable < build_fails < builds_unresolved < resolved`. The iterative arms do not pass through
here: they edit the source themselves and are scored in their own runner.

```bash
dotnet run --project src/HybridLens.CLI -- verify-repair     --from <runs>.jsonl --target path/to/Corpus.sln     --applier DeepSeek-V4-Pro --out verified.jsonl
```

**Transfer probe on an arbitrary solution** — a manifest may declare a reduced design through
`condition_signatures`, and extra `build_arguments` for a solution that cannot restore in the
execution environment. Behaviour is then measured by an external golden-master harness rather than
the corpus oracle.

```bash
dotnet run --project src/HybridLens.CLI -- external-oracle     --artifacts <campaign-dir>/final-sources --target path/to/Solution.sln     --harness path/to/Harness.csproj --golden path/to/golden     --harness-prop -p:ProductRoot={WORKING_ROOT}     --build-arg --no-restore --build-arg -p:NuGetAudit=false     --working-copy-skip bin --working-copy-skip .git --working-copy-skip .vs --working-copy-skip .idea
```

Building with `--no-restore` obliges the working copy to keep `obj`, because that is where
`project.assets.json` lives and nothing else can regenerate it. Omit it and MSBuild stops at
NETSDK1004 before the repaired file is ever compiled, so every assignment records a build failure the
model never caused — hence `--working-copy-skip` above, and `working_copy_skip_directories` in a
manifest. Both paths refuse the unsafe combination at preflight rather than produce that data.

Each artefact is evaluated in its own copy of the pristine tree with exactly one file replaced, so
no artefact can observe another. `{WORKING_ROOT}` is substituted with that copy, which is what makes
the harness measure the repaired tree rather than the pristine one. Outcomes are three-valued:
`behaviour_preserved`, `behavioural_change`, and `public_contract_change` for a harness that no
longer compiles because a repair moved members — that last is not a regression and is left for
adjudication.

### Analysis

```bash
python analysis/analyse_results.py --input "runs/*.jsonl" --output output
python analysis/extraction_vs_simplification.py --campaign experiments/<run>
python analysis/factorial_glmm.py --help
```

`extraction_vs_simplification.py` classifies every archived repair from its diff as an extraction or
a branch simplification. It is what turns the Goodhart concern about a metric-resolved outcome from
a caveat into a measurement.

### Help

```bash
dotnet run --project src/HybridLens.CLI -- --help
dotnet run --project src/HybridLens.CLI -- <command> --help
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
