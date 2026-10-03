# Pipeline modules

The pipeline orchestrates the repair experiments described in the revised thesis. It depends on
Core contracts and ContextBuilder prompt construction. Provider adapters live in `HybridLens.LLM`;
Roslyn measurement lives in `HybridLens.StaticAnalysis`. The CLI supplies those implementations.

| Responsibility | Module |
|---|---|
| Frozen factorial schedule and validation | `FactorialCampaignPlanner`, `FactorialCampaignManifestStore`, `FactorialCampaignPreflight` |
| Frozen context-ladder validation | `ContextLadderManifestStore` (schemas in Core) |
| Factorial assignment execution | `FactorialCampaignRunner` |
| Context assignment execution and bounded invocations | `ContextLadderCampaignRunner` |
| Resume validation and completion rows | `CampaignLedger<T>` |
| Per-assignment traces and record accounting | `RecordingRunStore`, backed by `JsonlRunStore` |
| One-call direct editing | `FactorialSingleShotRunner` |
| Compiler/visible-test feedback loop | `AgenticRunner` |
| Iterative response decoding and location matching | `AgenticResponseParser`, `AgenticFindingMatcher` |
| Isolated source copies | `WorkingCopy` |
| Compilation | `DotnetBuilder` |
| Post-repair behavioural evaluation | `PrivateLayer3Evaluator`, `ExternalOracleEvaluator` |
| Independent quality measurement | `ExternalQualityEvaluator`, `ISolutionQualityScanner` |

CLI commands parse options, resolve configured dependencies, invoke preflight, and map
`CampaignRunOutcome` to an exit status. Campaign services accept adapters, context builders,
measurers and a log writer explicitly; they do not read application configuration or use Console.
Invoke the corresponding manifest validation before calling a campaign service directly.

## Experimental invariants

- Keep frozen prompts, ladder versions, assignment identities and JSON field names compatible.
- Single-shot assignments make one evaluated-model call. Compiler/test results cannot trigger a retry.
- Iterative assignments share the frozen build-attempt budget. Only the assigned compiler and
  visible-test feedback enters the loop; detector remeasurement and private-oracle results do not.
- Context-ladder assignments use direct editing with visible tests disabled at every level.
- Provider failures remain recorded assignments; a committed failure must not be rerun on resume.
- Close the assignment trace before committing completion. Refuse orphan traces, malformed or
  foreign ledgers, duplicate completions and missing committed traces. Context ledgers also verify
  the trace hash. Preserve the existing factorial ledger schema, which has no trace-hash field.
- Keep private behavioural evaluation after repair; strict success combines separate final-state
  measurements and is not inferred from model text.
- Keep working copies isolated, including the declared `obj` retention for no-restore builds.

The older suggestion/applier workflow remains in `AnalysisPipeline`, `RepairApplier` and
`RepairVerifier` for compatibility with historical runs. It does not participate in the final
factorial or direct-edit context-ladder execution path.

## Verification

From the repository root:

```bash
dotnet build src/HybridLens.slnx
dotnet test src/HybridLens.Tests/HybridLens.Tests.csproj
```

`Campaigns/` tests cover ledger compatibility, stop/resume, partial or modified traces,
cancellation and provider-failure accounting. Existing runner tests exercise one-call versus
iterative feedback, blinded targets, visible-test handling and isolated working copies.
