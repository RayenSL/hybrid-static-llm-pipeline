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

### Analyse a project

```bash
dotnet run --project src/HybridLens.CLI -- analyse --target path/to/Project.csproj
```

### Analyse a solution

```bash
dotnet run --project src/HybridLens.CLI -- analyse --target path/to/Solution.sln
```

### With a custom config file

```bash
dotnet run --project src/HybridLens.CLI -- analyse --target path/to/Project.csproj --config path/to/hybridlens.json
```

### Single-model run (controlled experiment)

`analyse` uses every model in `Llm.Models` by default. Use `--model` to pin generation to one
evaluated model while keeping others (e.g. the verify-repair applier) configured:

```bash
dotnet run --project src/HybridLens.CLI -- analyse \
    --target path/to/Corpus.sln --context-level minimal --model gpt-5.4 --runs 3
```

`--model` accepts a comma-separated list; omit it to use all configured models.

### Help

```bash
dotnet run --project src/HybridLens.CLI -- --help
dotnet run --project src/HybridLens.CLI -- analyse --help
```

### Run the agentic arm (ungrounded, H1b)

`agentic` runs the third architecture arm (§4.4.1, prompt v2.0.0). The model gets the *unannotated*
whole file and must **detect and repair** it through an autonomous loop: each turn it edits the
source and requests a build (its **only** tool is the compiler), observes the result, and revises,
until it declares completion or the frozen iteration budget is spent. It never sees the static
analyser, so the arm stays ungrounded. Self-detections are matched to the known instances for
recall/precision, and the agent's *final edited solution* is scored directly for verified-repair
(no separate applier — see below).

```bash
dotnet run --project src/HybridLens.CLI -- agentic \
    --from runs/<structural-trace>.jsonl \
    --target path/to/Corpus.sln \
    --model gpt-5.4 --runs 3 --budget 6
```

By default the agent runs over the files holding a seeded instance. Add `--sweep-corpus` to run it
over every `.cs` (incl. clean/distractor files) so detections on non-instances score as spurious
(fuller precision). Each trajectory (all turns + build results + final source) is frozen as a JSON
artefact under `runs/<stamp>-agentic-trajectories/`.

### Verify repairs (objective repair outcome)

`verify-repair` takes the repairs the **hybrid** arm produced (the `parsed_suggested_fix` of each
hybrid run), applies each one strict-literally with a non-evaluated **applier**, rebuilds the corpus,
and re-measures the metric that triggered the detection. Each candidate is scored on the ladder
`unapplicable < build_fails < builds_unresolved < resolved`, plus a binary `verified_repair_success`
(applies ∧ builds ∧ metric-resolved). The agentic arm is **not** processed here — the agent edits the
source itself, so its final solution is scored inside the `agentic` runner (§4.7.1).

```bash
dotnet run --project src/HybridLens.CLI -- verify-repair \
    --from runs/20260101-120000.jsonl \
    --target path/to/Corpus.sln \
    --applier DeepSeek-V4-Pro \
    --out runs/verified.jsonl
```

The applier must be a model **different from the evaluated model** (so it never scores code it
completed itself). `DeepSeek-V4-Pro` (Azure) is the default and reuses your Azure config — no extra
provider/key:

```json
// appsettings.local.json
{
  "Llm": {
    "Models": {
      "DeepSeek-V4-Pro": { "Provider": "azure", "Model": "DeepSeek-V4-Pro", "BaseUrl": "https://<your>.openai.azure.com" }
    }
  }
}
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
      "gpt-5.4":         { "Provider": "azure",  "Model": "gpt-5.4", "BaseUrl": "https://<your>.openai.azure.com" },
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
| `azure` | Azure OpenAI (e.g. `gpt-5.4`) — requires `BaseUrl` + `ApiKey` |

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
