using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Executes the frozen factorial schedule without exposing post-repair oracles to repair.</summary>
public sealed class FactorialCampaignRunner(
    ILlmAdapter adapter, IContextBuilder contextBuilder, IRepairMeasurer measurer)
{
    public async Task<CampaignRunOutcome> RunAsync(
        FactorialCampaignManifest manifest, string outputDirectory,
        IReadOnlyDictionary<string, LoadedGeneratedTest> visibleByArtifact,
        TextWriter log, CancellationToken cancellationToken = default)
    {
        var root = Path.GetFullPath(outputDirectory);
        var traces = Path.Combine(root, "traces");
        var trajectories = Path.Combine(root, "trajectories");
        var finalSources = Path.Combine(root, "final-sources");
        var ledgerPath = Path.Combine(root, "execution-ledger.jsonl");
        Directory.CreateDirectory(traces);
        Directory.CreateDirectory(trajectories);
        Directory.CreateDirectory(finalSources);

        var ledger = new CampaignLedger<FactorialCampaignExecutionRecord>(ledgerPath, manifest.CampaignId);
        Dictionary<string, FactorialCampaignExecutionRecord> completed;
        try { completed = ledger.LoadCompleted(); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            await log.WriteLineAsync($"error: resume preflight failed: {ex.Message}");
            return CampaignRunOutcome.InvalidResumeState;
        }

        var structural = new ContextConfig { Level = ContextLevel.Structural };

        // A manifest may carry extra dotnet build arguments for solutions that cannot restore
        // in this environment. Absent them the gate keeps its default command line.
        var buildArguments = manifest.BuildArguments is { Count: > 0 } extra ? extra : null;
        // A solution built with --no-restore must keep obj/ in the working copy, or MSBuild
        // fails with NETSDK1004 before the repair is ever compiled.
        var skipDirectories = manifest.WorkingCopySkipDirectories;
        Func<string, int, CancellationToken, Task<(bool Ok, string Output)>>? build = buildArguments is null
            ? null
            : (solution, timeout, token) => DotnetBuilder.BuildAsync(solution, timeout, buildArguments, token);

        log.WriteLine($"Campaign: {manifest.CampaignId}"
            + (manifest.Kind is null ? "" : $"  kind: {manifest.Kind}"));
        if (buildArguments is not null)
            log.WriteLine($"Build arguments: {string.Join(' ', buildArguments)}");
        log.WriteLine("Working copy omits: "
            + string.Join(' ', skipDirectories ?? FactorialSingleShotRunner.DefaultSkipDirs));
        log.WriteLine(
            $"Design: {string.Join(", ", FactorialCampaignPlanner.ExpectedSignatures(manifest))}");
        log.WriteLine($"Assignments: {manifest.Assignments.Count}; already completed: {completed.Count}");

        foreach (var assignment in manifest.Assignments.OrderBy(a => a.Order))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (completed.ContainsKey(assignment.AssignmentId)) continue;
            var tracePath = Path.Combine(traces, $"{assignment.Order:D4}-{assignment.AssignmentId}.jsonl");
            if (File.Exists(tracePath))
            {
                await log.WriteLineAsync(
                    $"error: incomplete assignment trace already exists; quarantine it before resuming: {tracePath}");
                return CampaignRunOutcome.InvalidResumeState;
            }

            await using var store = new RecordingRunStore(tracePath);
            try
            {
                var known = KnownInstance.Create(
                    assignment.AntiPatternType,
                    assignment.FilePath,
                    assignment.SymbolName,
                    assignment.Line,
                    assignment.Severity,
                    assignment.Snippet) with { EndLine = assignment.TargetEndLine };
                var finding = new Finding
                {
                    Type = assignment.AntiPatternType,
                    Severity = assignment.Severity,
                    FilePath = assignment.FilePath,
                    SymbolName = assignment.SymbolName,
                    Line = assignment.Line,
                    Snippet = assignment.Snippet,
                    Metrics = new Dictionary<string, double>(assignment.Metrics, StringComparer.Ordinal)
                };
                var groundingBlock = assignment.GroundingEnabled
                    ? contextBuilder.Build(finding, [finding], structural).UserPrompt
                    : null;
                var visible = assignment.VisibleTestArtifactRef is null
                    ? null
                    : visibleByArtifact[Path.GetFullPath(assignment.VisibleTestArtifactRef)];

                if (assignment.ControlStructure == "single_shot")
                {
                    var runner = new FactorialSingleShotRunner(
                        adapter,
                        manifest.ModelName,
                        measurer,
                        manifest.TargetSolution,
                        manifest.BuildTimeoutSeconds,
                        build,
                        workingCopySkipDirectories: skipDirectories);
                    var record = await runner.RunAttemptAsync(
                        known,
                        assignment.RunNumber,
                        assignment.GroundingEnabled,
                        groundingBlock,
                        assignment.VisibleTestsEnabled,
                        visible,
                        finalSources,
                        cancellationToken);
                    await store.AppendAsync(record, cancellationToken);
                }
                else
                {
                    var architecture = assignment.GroundingEnabled ? "grounded_iterative" : "agentic";
                    var grounding = assignment.GroundingEnabled
                        ? new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
                        {
                            [Path.GetFullPath(assignment.FilePath)] = groundingBlock!
                        }
                        : null;
                    var visibleByFile = visible is null
                        ? new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase)
                        : new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase)
                        {
                            [Path.GetFullPath(assignment.FilePath)] = visible
                        };
                    var runner = new AgenticRunner(
                        adapter,
                        manifest.ModelName,
                        measurer,
                        manifest.TargetSolution,
                        manifest.IterationBudget,
                        manifest.BuildTimeoutSeconds,
                        build,
                        architecture: architecture,
                        workingCopySkipDirectories: skipDirectories);
                    await runner.RunAsync(
                        [known],
                        runs: 1,
                        store,
                        manifest.MaxInputTokenGuard,
                        trajectories,
                        log,
                        cancellationToken,
                        sweepFiles: [assignment.FilePath],
                        groundingByFile: grounding,
                        visibleTestsByFile: visibleByFile,
                        visibleTestsEnabled: assignment.VisibleTestsEnabled,
                        finalArtifactDirectory: finalSources,
                        runNumberOffset: assignment.RunNumber - 1);
                }

                await store.FlushAsync(cancellationToken);
                var execution = new FactorialCampaignExecutionRecord
                {
                    CampaignId = manifest.CampaignId,
                    AssignmentId = assignment.AssignmentId,
                    Order = assignment.Order,
                    Timestamp = DateTimeOffset.UtcNow,
                    Completed = true,
                    TraceFile = Path.GetFullPath(tracePath),
                    RunIds = store.RunIds.ToList()
                };
                await ledger.AppendAsync(execution, cancellationToken);
                completed[assignment.AssignmentId] = execution;
                log.WriteLine(
                    $"[{assignment.Order}/{manifest.Assignments.Count}] {assignment.AssignmentId}: " +
                    $"grounded={assignment.GroundingEnabled}, control={assignment.ControlStructure}, " +
                    $"tests={assignment.VisibleTestsEnabled} complete");
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                await ledger.AppendAsync(new FactorialCampaignExecutionRecord
                {
                    CampaignId = manifest.CampaignId,
                    AssignmentId = assignment.AssignmentId,
                    Order = assignment.Order,
                    Timestamp = DateTimeOffset.UtcNow,
                    Completed = false,
                    TraceFile = Path.GetFullPath(tracePath),
                    RunIds = store.RunIds.ToList(),
                    Error = ex.Message
                }, cancellationToken);
                await log.WriteLineAsync($"error: assignment {assignment.AssignmentId} failed: {ex.Message}");
                return CampaignRunOutcome.AssignmentFailed;
            }
        }

        log.WriteLine("Factorial campaign complete. Freeze the output directory before private evaluation.");
        return CampaignRunOutcome.Completed;
    }
}
