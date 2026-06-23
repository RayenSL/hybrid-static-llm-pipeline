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

### Help

```bash
dotnet run --project src/HybridLens.CLI -- --help
dotnet run --project src/HybridLens.CLI -- analyse --help
```

### Verify repairs (objective repair outcome)

`verify-repair` takes the repairs an LLM produced (the `parsed_suggested_fix` of each hybrid /
matched llm-only run), applies each one strict-literally with a non-evaluated Claude-family
**applier**, rebuilds the corpus, and re-measures the metric that triggered the detection. Each
candidate is scored on the ladder `unapplicable < build_fails < builds_unresolved < resolved`,
plus a binary `verified_repair_success` (applies ∧ builds ∧ metric-resolved).

```bash
dotnet run --project src/HybridLens.CLI -- verify-repair \
    --from runs/20260101-120000.jsonl \
    --target path/to/Corpus.sln \
    --applier claude-opus-4-8 \
    --out runs/verified.jsonl
```

The applier must be a Claude-family model **different from the evaluated model** (so it never
scores code it completed itself). Add it as a model entry in `appsettings.local.json`:

```json
// appsettings.local.json
{
  "Llm": {
    "Models": {
      "claude-opus-4-8": { "Provider": "claude", "Model": "claude-opus-4-8", "ApiKey": "sk-ant-..." }
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
      "MaxMethods": 20,
      "MaxFields": 15,
      "MaxLinesOfCode": 500
    },
    "LongMethod": {
      "MaxLinesOfCode": 50,
      "MaxCyclomaticComplexity": 10
    },
    "ObsoleteApi": {
      "DeprecatedNamespacePrefixes": []
    }
  },
  "Context": {
    "Strategy": "PerFinding",
    "TokenBudget": 2000,
    "SnippetContextLines": 10,
    "TemplateDirectory": "templates",
    "Metadata": {}
  },
  "Llm": {
    "Provider": "claude",
    "Model": "claude-sonnet-4-6",
    "Temperature": 0.2,
    "MaxTokens": 1024
  }
}
```

#### Detector thresholds

| Key | Default | Description |
|---|---|---|
| `Detectors.GodClass.MaxMethods` | `20` | Method count above which a class is flagged |
| `Detectors.GodClass.MaxFields` | `15` | Field count above which a class is flagged |
| `Detectors.GodClass.MaxLinesOfCode` | `500` | LOC above which a class is flagged |
| `Detectors.LongMethod.MaxLinesOfCode` | `50` | LOC above which a method is flagged |
| `Detectors.LongMethod.MaxCyclomaticComplexity` | `10` | Complexity above which a method is flagged |
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
| `claude` | Requires `Llm.ApiKey` set in `appsettings.local.json` |
| `openai` | Requires `Llm.ApiKey` set in `appsettings.local.json` |

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
