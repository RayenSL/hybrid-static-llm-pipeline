using System.CommandLine;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Executes a frozen Minimal/Structural/Relational/Full Hybrid campaign one assignment at a time.
/// Each assignment contains one evaluated-model explanation/remediation call followed, when a remediation
/// parses, by one strict-literal applier call. Per-assignment traces and an append-only ledger make the
/// campaign restartable without repeating completed calls.
/// </summary>
public static class GroundingCampaignCommand
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    private static readonly JsonSerializerOptions LedgerJson = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    public static Command Build(IServiceProvider services)
    {
        var manifestOption = new Option<FileInfo>("--manifest")
        {
            Required = true,
            Description = "Frozen four-level grounding campaign manifest."
        };
        var outOption = new Option<DirectoryInfo>("--out")
        {
            Required = true,
            Description = "New or resumable campaign output directory."
        };
        var preflightOption = new Option<bool>("--preflight-only")
        {
            Description = "Validate the complete manifest and configured models without making a model call."
        };
        var stopAfterOption = new Option<int>("--stop-after")
        {
            Description = "Stop successfully after N new assignments (0 = run all remaining)."
        };

        var command = new Command(
            "grounding-campaign",
            "Execute or resume a frozen Minimal/Structural/Relational/Full Hybrid experiment.")
        {
            manifestOption, outOption, preflightOption, stopAfterOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var manifestFile = parseResult.GetValue(manifestOption)!;
            var outputDirectory = parseResult.GetValue(outOption)!;
            var preflightOnly = parseResult.GetValue(preflightOption);
            var stopAfter = Math.Max(0, parseResult.GetValue(stopAfterOption));

            GroundingCampaignManifest manifest;
            try
            {
                manifest = LoadAndValidate(manifestFile.FullName);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: grounding manifest preflight failed: {ex.Message}");
                return 2;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(manifest.ModelName, out _))
            {
                await Console.Error.WriteLineAsync($"error: evaluated model '{manifest.ModelName}' is not configured");
                return 2;
            }
            if (!adapters.TryGetValue(manifest.ApplierModel, out var applierAdapter))
            {
                await Console.Error.WriteLineAsync($"error: applier model '{manifest.ApplierModel}' is not configured");
                return 2;
            }
            if (manifest.PromptVersion != PromptTemplate.Version ||
                manifest.ApplierPromptVersion != PromptTemplate.ApplierVersion)
            {
                await Console.Error.WriteLineAsync(
                    $"error: prompt version drift (manifest {manifest.PromptVersion}/{manifest.ApplierPromptVersion}; " +
                    $"runtime {PromptTemplate.Version}/{PromptTemplate.ApplierVersion})");
                return 2;
            }

            Console.Error.WriteLine($"Campaign: {manifest.CampaignId}");
            Console.Error.WriteLine($"Manifest SHA-256: {Sha256File(manifestFile.FullName)}");
            Console.Error.WriteLine(
                $"Assignments: {manifest.Assignments.Count}; model={manifest.ModelName}; " +
                $"applier={manifest.ApplierModel}; repetitions={manifest.Repetitions}");
            if (preflightOnly)
            {
                Console.Error.WriteLine("Grounding campaign preflight passed; no model call made.");
                return 0;
            }

            var root = Path.GetFullPath(outputDirectory.FullName);
            var traces = Path.Combine(root, "traces");
            var finalSources = Path.Combine(root, "final-sources");
            var ledgerPath = Path.Combine(root, "execution-ledger.jsonl");
            Directory.CreateDirectory(traces);
            Directory.CreateDirectory(finalSources);

            Dictionary<string, GroundingExecutionRecord> completed;
            try
            {
                completed = LoadCompleted(ledgerPath, manifest.CampaignId);
                foreach (var prior in completed.Values)
                {
                    if (!File.Exists(prior.TraceFile))
                        throw new InvalidDataException(
                            $"completed assignment {prior.AssignmentId} has no trace: {prior.TraceFile}");
                    if (Sha256File(prior.TraceFile) != prior.TraceSha256)
                        throw new InvalidDataException(
                            $"completed assignment trace hash changed: {prior.AssignmentId}");
                }
            }
            catch (Exception ex)
            {
                await Console.Error.WriteLineAsync($"error: resume preflight failed: {ex.Message}");
                return 2;
            }

            var contextConfig = services.GetRequiredService<ContextConfig>();
            var pipeline = services.GetRequiredService<AnalysisPipeline>();
            var measurer = services.GetRequiredService<IRepairMeasurer>();
            var modelFilter = new HashSet<string>([manifest.ModelName], StringComparer.OrdinalIgnoreCase);
            var applier = new RepairApplier(applierAdapter, manifest.ApplierModel);
            var executedThisInvocation = 0;
            Console.Error.WriteLine($"Already completed: {completed.Count}");

            foreach (var assignment in manifest.Assignments.OrderBy(a => a.Order))
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (completed.ContainsKey(assignment.AssignmentId)) continue;
                if (stopAfter > 0 && executedThisInvocation >= stopAfter) break;

                var tracePath = Path.Combine(traces, $"{assignment.Order:D4}-{assignment.AssignmentId}.jsonl");
                if (File.Exists(tracePath))
                {
                    await Console.Error.WriteLineAsync(
                        $"error: incomplete assignment trace already exists; quarantine it before resuming: {tracePath}");
                    return 2;
                }

                await using var store = new RecordingRunStore(tracePath);
                try
                {
                    contextConfig.Level = assignment.ContextLevel;
                    contextConfig.Metadata = new Dictionary<string, string>(
                        assignment.ProjectMetadata, StringComparer.Ordinal);
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

                    await pipeline.RunAsync(
                        [finding], assignment.Severity, runs: 1, store, modelFilter, cancellationToken);
                    var generation = store.Records.SingleOrDefault(r => r.SourceRunId is null)
                        ?? throw new InvalidDataException("assignment did not emit one generation record");
                    var applierCalled = false;
                    if (!string.IsNullOrWhiteSpace(generation.ParsedSuggestedFix))
                    {
                        applierCalled = true;
                        var candidate = new RepairCandidate
                        {
                            SourceRunId = generation.RunId,
                            Type = generation.AntiPatternType,
                            FilePath = generation.FilePath,
                            SymbolName = generation.SymbolName,
                            Line = generation.Line,
                            Severity = generation.Severity,
                            Snippet = generation.Snippet,
                            Metrics = generation.Metrics,
                            ContextLevel = generation.ContextLevel,
                            ModelName = generation.ModelName,
                            PromptVersion = generation.PromptVersion,
                            Architecture = generation.Architecture ?? "hybrid",
                            RunNumber = generation.RunNumber,
                            RepairText = generation.ParsedSuggestedFix
                        };
                        var verifier = new RepairVerifier(
                            applier, measurer, manifest.TargetSolution, manifest.BuildTimeoutSeconds);
                        await verifier.RunAsync(
                            [candidate], store, Console.Error, cancellationToken,
                            finalArtifactDirectory: finalSources);
                    }

                    await store.FlushAsync(cancellationToken);
                    var execution = new GroundingExecutionRecord
                    {
                        CampaignId = manifest.CampaignId,
                        AssignmentId = assignment.AssignmentId,
                        Order = assignment.Order,
                        ContextLevel = assignment.ContextLevel,
                        Timestamp = DateTimeOffset.UtcNow,
                        Completed = true,
                        TraceFile = Path.GetFullPath(tracePath),
                        TraceSha256 = Sha256File(tracePath),
                        RunIds = store.Records.Select(r => r.RunId).ToList(),
                        EvaluatedModelCalls = 1,
                        ApplierCalls = applierCalled ? 1 : 0,
                        InputTokens = store.Records.Sum(r => r.InputTokens ?? 0),
                        OutputTokens = store.Records.Sum(r => r.OutputTokens ?? 0)
                    };
                    await AppendLedgerAsync(ledgerPath, execution, cancellationToken);
                    completed[assignment.AssignmentId] = execution;
                    executedThisInvocation++;
                    var verification = store.Records.SingleOrDefault(r => r.SourceRunId is not null);
                    var outcome = verification?.VerifiedRepairLadder?.ToString()
                                  ?? generation.ErrorStatus?.ToString()
                                  ?? "NoRemediation";
                    Console.Error.WriteLine(
                        $"[{assignment.Order}/{manifest.Assignments.Count}] {assignment.ContextLevel} " +
                        $"{assignment.AntiPatternType} {assignment.SymbolName} -> {outcome}");
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex)
                {
                    await store.FlushAsync(cancellationToken);
                    await AppendLedgerAsync(ledgerPath, new GroundingExecutionRecord
                    {
                        CampaignId = manifest.CampaignId,
                        AssignmentId = assignment.AssignmentId,
                        Order = assignment.Order,
                        ContextLevel = assignment.ContextLevel,
                        Timestamp = DateTimeOffset.UtcNow,
                        Completed = false,
                        TraceFile = Path.GetFullPath(tracePath),
                        TraceSha256 = File.Exists(tracePath) ? Sha256File(tracePath) : string.Empty,
                        RunIds = store.Records.Select(r => r.RunId).ToList(),
                        EvaluatedModelCalls = store.Records.Any(r => r.SourceRunId is null) ? 1 : 0,
                        ApplierCalls = store.Records.Any(r => r.SourceRunId is not null) ? 1 : 0,
                        InputTokens = store.Records.Sum(r => r.InputTokens ?? 0),
                        OutputTokens = store.Records.Sum(r => r.OutputTokens ?? 0),
                        Error = ex.Message
                    }, cancellationToken);
                    await Console.Error.WriteLineAsync(
                        $"error: assignment {assignment.AssignmentId} failed: {ex.Message}");
                    return 1;
                }
            }

            Console.Error.WriteLine(
                $"Grounding campaign invocation complete: new={executedThisInvocation}, " +
                $"total={completed.Count}/{manifest.Assignments.Count}.");
            return 0;
        });
        return command;
    }

    private static GroundingCampaignManifest LoadAndValidate(string path)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("manifest not found", path);
        var manifest = JsonSerializer.Deserialize<GroundingCampaignManifest>(
            File.ReadAllText(path), JsonOptions)
            ?? throw new InvalidDataException("manifest is empty or invalid");
        if (manifest.SchemaVersion != "1.0.0")
            throw new InvalidDataException("unsupported grounding manifest schema");
        if (manifest.Repetitions != 1)
            throw new InvalidDataException("this frozen grounding campaign must use one repetition");
        if (manifest.Assignments.Count != 120)
            throw new InvalidDataException("grounding campaign must contain 120 assignments");
        if (!File.Exists(manifest.TargetSolution) ||
            !Path.GetExtension(manifest.TargetSolution).Equals(".sln", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("target solution not found", manifest.TargetSolution);
        if (!File.Exists(manifest.BaselineSource) || Sha256File(manifest.BaselineSource) != manifest.BaselineSha256)
            throw new InvalidDataException("frozen analyzer baseline is missing or changed");
        if (manifest.Assignments.Select(a => a.AssignmentId).Distinct(StringComparer.Ordinal).Count() != 120)
            throw new InvalidDataException("assignment IDs are not unique");
        if (manifest.Assignments.Select(a => a.Order).Order().SequenceEqual(Enumerable.Range(1, 120)) is false)
            throw new InvalidDataException("assignment order must be exactly 1..120");

        var allowed = new HashSet<ContextLevel>
        {
            ContextLevel.Minimal, ContextLevel.Structural,
            ContextLevel.Relational, ContextLevel.Full
        };
        var blocks = manifest.Assignments.GroupBy(a => a.BlockId, StringComparer.Ordinal).ToList();
        if (blocks.Count != 30 || blocks.Any(b => b.Count() != 4 || !b.Select(a => a.ContextLevel).ToHashSet().SetEquals(allowed)))
            throw new InvalidDataException("each of 30 target blocks must contain all four context levels exactly once");
        var typeCounts = blocks.Select(b => b.First().AntiPatternType).ToLookup(x => x);
        if (typeCounts[AntiPatternType.GodClass].Count() != 10 ||
            typeCounts[AntiPatternType.LongMethod].Count() != 10 ||
            typeCounts[AntiPatternType.ObsoleteApiUsage].Count() != 10)
            throw new InvalidDataException("campaign must contain 10 independent targets per anti-pattern");

        foreach (var assignment in manifest.Assignments)
        {
            if (!File.Exists(assignment.FilePath) || Sha256File(assignment.FilePath) != assignment.PristineSourceSha256)
                throw new InvalidDataException($"pristine source missing or changed: {assignment.AssignmentId}");
            if (assignment.RunNumber != 1)
                throw new InvalidDataException("all assignments must use run number 1");
            if (assignment.ProjectMetadata.Count == 0 ||
                !assignment.ProjectMetadata.ContainsKey("Framework") ||
                !assignment.ProjectMetadata.ContainsKey("Project") ||
                !assignment.ProjectMetadata.ContainsKey("Domain"))
                throw new InvalidDataException($"project metadata incomplete: {assignment.AssignmentId}");
        }
        return manifest;
    }

    private static Dictionary<string, GroundingExecutionRecord> LoadCompleted(
        string ledgerPath, string campaignId)
    {
        var result = new Dictionary<string, GroundingExecutionRecord>(StringComparer.Ordinal);
        if (!File.Exists(ledgerPath)) return result;
        foreach (var line in File.ReadLines(ledgerPath))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var record = JsonSerializer.Deserialize<GroundingExecutionRecord>(line, LedgerJson)
                ?? throw new InvalidDataException("execution ledger contains an invalid row");
            if (record.CampaignId != campaignId)
                throw new InvalidDataException("execution ledger belongs to a different campaign");
            if (record.Completed && !result.TryAdd(record.AssignmentId, record))
                throw new InvalidDataException($"duplicate completed assignment: {record.AssignmentId}");
        }
        return result;
    }

    private static async Task AppendLedgerAsync(
        string ledgerPath, GroundingExecutionRecord record, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(ledgerPath)!);
        await File.AppendAllTextAsync(
            ledgerPath,
            JsonSerializer.Serialize(record, LedgerJson) + Environment.NewLine,
            new UTF8Encoding(false),
            cancellationToken);
    }

    private static string Sha256File(string path)
        => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    private sealed class RecordingRunStore(string tracePath) : IRunStore
    {
        private readonly JsonlRunStore _inner = new(tracePath);
        private bool _closed;
        public List<RunRecord> Records { get; } = [];

        public async Task AppendAsync(RunRecord record, CancellationToken cancellationToken = default)
        {
            if (_closed) throw new ObjectDisposedException(nameof(RecordingRunStore));
            await _inner.AppendAsync(record, cancellationToken);
            Records.Add(record);
        }

        public async Task FlushAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await CloseAsync();
        }

        public ValueTask DisposeAsync() => CloseAsync();

        private async ValueTask CloseAsync()
        {
            if (_closed) return;
            _closed = true;
            await _inner.DisposeAsync();
        }
    }

    private sealed record GroundingCampaignManifest
    {
        public required string SchemaVersion { get; init; }
        public required string CampaignId { get; init; }
        public required string ModelName { get; init; }
        public required string ApplierModel { get; init; }
        public required string TargetSolution { get; init; }
        public required string BaselineSource { get; init; }
        public required string BaselineSha256 { get; init; }
        public required string CodeRevision { get; init; }
        public required string PromptVersion { get; init; }
        public required string ApplierPromptVersion { get; init; }
        public required int Repetitions { get; init; }
        public required int RandomizationSeed { get; init; }
        public required int BuildTimeoutSeconds { get; init; }
        public required List<GroundingAssignment> Assignments { get; init; }
    }

    private sealed record GroundingAssignment
    {
        public required int Order { get; init; }
        public required string AssignmentId { get; init; }
        public required string BlockId { get; init; }
        public required int RunNumber { get; init; }
        public required ContextLevel ContextLevel { get; init; }
        public required AntiPatternType AntiPatternType { get; init; }
        public required Severity Severity { get; init; }
        public required string FilePath { get; init; }
        public required string SymbolName { get; init; }
        public required int Line { get; init; }
        public string? Snippet { get; init; }
        public required Dictionary<string, double> Metrics { get; init; }
        public required List<string> ExpectedQualityAttributes { get; init; }
        public required string PristineSourceSha256 { get; init; }
        public required Dictionary<string, string> ProjectMetadata { get; init; }
    }

    private sealed record GroundingExecutionRecord
    {
        public required string CampaignId { get; init; }
        public required string AssignmentId { get; init; }
        public required int Order { get; init; }
        public required ContextLevel ContextLevel { get; init; }
        public required DateTimeOffset Timestamp { get; init; }
        public required bool Completed { get; init; }
        public required string TraceFile { get; init; }
        public required string TraceSha256 { get; init; }
        public required List<string> RunIds { get; init; }
        public required int EvaluatedModelCalls { get; init; }
        public required int ApplierCalls { get; init; }
        public required int InputTokens { get; init; }
        public required int OutputTokens { get; init; }
        public string? Error { get; init; }
    }
}
