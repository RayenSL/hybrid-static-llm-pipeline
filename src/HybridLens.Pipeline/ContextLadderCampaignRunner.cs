using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>Runs matched context levels with one direct-edit call and no visible-test feedback.</summary>
public sealed class ContextLadderCampaignRunner(
    ILlmAdapter adapter, IContextBuilder contextBuilder, IRepairMeasurer measurer)
{
    public async Task<CampaignRunOutcome> RunAsync(
        ContextLadderManifest manifest, string outputDirectory, int stopAfter,
        TextWriter log, CancellationToken cancellationToken = default)
    {
        var ladder = ContextLadder.ForVersion(manifest.LadderVersion);
        var root = Path.GetFullPath(outputDirectory);
        var traces = Path.Combine(root, "traces");
        var finalSources = Path.Combine(root, "final-sources");
        var ledgerPath = Path.Combine(root, "execution-ledger.jsonl");
        Directory.CreateDirectory(traces);
        Directory.CreateDirectory(finalSources);

        var ledger = new CampaignLedger<LadderExecutionRecord>(ledgerPath, manifest.CampaignId);
        Dictionary<string, LadderExecutionRecord> completed;
        try
        {
            completed = ledger.LoadCompleted(record => record.TraceSha256);
        }
        catch (Exception ex)
        {
            await log.WriteLineAsync($"error: resume preflight failed: {ex.Message}");
            return CampaignRunOutcome.InvalidResumeState;
        }

        var executedThisInvocation = 0;
        log.WriteLine($"Already completed: {completed.Count}");

        foreach (var assignment in manifest.Assignments.OrderBy(a => a.Order))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (completed.ContainsKey(assignment.AssignmentId)) continue;
            if (stopAfter > 0 && executedThisInvocation >= stopAfter) break;

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
                var finding = new Finding
                {
                    Type = assignment.AntiPatternType,
                    Severity = assignment.Severity,
                    FilePath = assignment.FilePath,
                    SymbolName = assignment.SymbolName,
                    Line = assignment.Line,
                    Snippet = assignment.Snippet,
                    Metrics = new Dictionary<string, double>(assignment.Metrics, StringComparer.Ordinal),
                    ExpectedQualityAttributes = assignment.ExpectedQualityAttributes
                };

                // The level's whole meaning comes from the ladder; the cross-file payload was
                // resolved during preflight and travels frozen in the manifest.
                var config = new ContextConfig
                {
                    Level = assignment.ContextLevel,
                    Ladder = ladder,
                    Metadata = new Dictionary<string, string>(assignment.ProjectMetadata, StringComparer.Ordinal),
                    CrossFileDeclarations = assignment.CrossFileDeclarations
                };
                var contextBlock = contextBuilder.Build(finding, [finding], config).UserPrompt;

                var known = KnownInstance.Create(
                    assignment.AntiPatternType, assignment.FilePath, assignment.SymbolName,
                    assignment.Line, assignment.Severity, assignment.Snippet)
                    with { EndLine = assignment.TargetEndLine };

                var runner = new FactorialSingleShotRunner(
                    adapter, manifest.ModelName, measurer, manifest.TargetSolution,
                    manifest.BuildTimeoutSeconds);

                // Visible tests stay off across the whole ladder: the supplement disabled them
                // and adding the factor here would confound the context dose.
                var record = await runner.RunAttemptAsync(
                    known,
                    assignment.RunNumber,
                    grounded: true,
                    groundingBlock: contextBlock,
                    visibleTestsEnabled: false,
                    visibleTest: null,
                    finalArtifactDirectory: finalSources,
                    cancellationToken: cancellationToken,
                    promptProfile: ContextLadderPrompt.Profile(
                        assignment.ContextLevel, assignment.CrossFileTruncated));
                await store.AppendAsync(record, cancellationToken);
                await store.FlushAsync(cancellationToken);

                var execution = new LadderExecutionRecord
                {
                    CampaignId = manifest.CampaignId,
                    AssignmentId = assignment.AssignmentId,
                    Order = assignment.Order,
                    ContextLevel = assignment.ContextLevel,
                    Timestamp = DateTimeOffset.UtcNow,
                    Completed = true,
                    TraceFile = Path.GetFullPath(tracePath),
                    TraceSha256 = FactorialCampaignPlanner.Sha256File(tracePath),
                    RunIds = store.Records.Select(r => r.RunId).ToList(),
                    EvaluatedModelCalls = 1,
                    CrossFileFiles = assignment.CrossFileDeclarations.Count,
                    CrossFileTruncated = assignment.CrossFileTruncated,
                    InputTokens = store.Records.Sum(r => r.InputTokens ?? 0),
                    OutputTokens = store.Records.Sum(r => r.OutputTokens ?? 0)
                };
                await ledger.AppendAsync(execution, cancellationToken);
                completed[assignment.AssignmentId] = execution;
                executedThisInvocation++;

                var outcome = record.VerifiedRepairLadder?.ToString()
                              ?? record.ErrorStatus?.ToString()
                              ?? "NoEdit";
                log.WriteLine(
                    $"[{assignment.Order}/{manifest.Assignments.Count}] {assignment.ContextLevel} " +
                    $"{assignment.AntiPatternType} {assignment.SymbolName} -> {outcome}");
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                await store.FlushAsync(cancellationToken);
                await ledger.AppendAsync(new LadderExecutionRecord
                {
                    CampaignId = manifest.CampaignId,
                    AssignmentId = assignment.AssignmentId,
                    Order = assignment.Order,
                    ContextLevel = assignment.ContextLevel,
                    Timestamp = DateTimeOffset.UtcNow,
                    Completed = false,
                    TraceFile = Path.GetFullPath(tracePath),
                    TraceSha256 = File.Exists(tracePath) ? FactorialCampaignPlanner.Sha256File(tracePath) : string.Empty,
                    RunIds = store.Records.Select(r => r.RunId).ToList(),
                    EvaluatedModelCalls = store.Records.Count,
                    CrossFileFiles = assignment.CrossFileDeclarations.Count,
                    CrossFileTruncated = assignment.CrossFileTruncated,
                    InputTokens = store.Records.Sum(r => r.InputTokens ?? 0),
                    OutputTokens = store.Records.Sum(r => r.OutputTokens ?? 0),
                    Error = ex.Message
                }, cancellationToken);
                await log.WriteLineAsync(
                    $"error: assignment {assignment.AssignmentId} failed: {ex.Message}");
                return CampaignRunOutcome.AssignmentFailed;
            }
        }

        log.WriteLine(
            $"Context ladder invocation complete: new={executedThisInvocation}, " +
            $"total={completed.Count}/{manifest.Assignments.Count}.");
        return CampaignRunOutcome.Completed;
    }
}
