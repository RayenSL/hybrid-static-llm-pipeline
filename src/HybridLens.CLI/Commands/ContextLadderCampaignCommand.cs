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
/// Executes a frozen Minimal/Structural/Relational/Full context ladder on the direct-editing
/// architecture (§4.4.3).
///
/// The sealed four-level supplement ran through suggestion-plus-applier, and 66% of its assignments
/// never reached a build: a non-evaluated strict-literal applier refused every God Class
/// recommendation and almost every Obsolete API one, so the outcome measured that applier's
/// contract rather than the context dose. This command removes the applier entirely. One evaluated
/// call per assignment returns the complete edited file, exactly as the confirmatory factorial
/// does, which is what makes an RQ3 answer transfer to the architecture the thesis recommends.
///
/// The manifest carries the ladder version and its hash. The campaign refuses to start if the
/// compiled ladder differs, so a definition edited after freezing cannot silently produce
/// assignments attributed to the old definition.
/// </summary>
public static class ContextLadderCampaignCommand
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
        var manifestOption = new Option<FileInfo?>("--manifest")
        {
            Description = "Frozen direct-edit context ladder manifest. Required unless --print-ladder is used."
        };
        var printLadderOption = new Option<string?>("--print-ladder")
        {
            Description = "Print a ladder definition and its hash, then exit. "
                        + $"One of {ContextLadder.V1Version}, {ContextLadder.V2Version}. "
                        + "The hash is what a manifest must carry as ladder_sha256."
        };
        var outOption = new Option<DirectoryInfo?>("--out")
        {
            Description = "New or resumable campaign output directory. Required unless --print-ladder is used."
        };
        var preflightOption = new Option<bool>("--preflight-only")
        {
            Description = "Validate the manifest, ladder hash and configured model without making a model call."
        };
        var stopAfterOption = new Option<int>("--stop-after")
        {
            Description = "Stop successfully after N new assignments (0 = run all remaining)."
        };

        var command = new Command(
            "context-ladder-campaign",
            "Execute or resume a frozen four-level context ladder under direct editing (no applier).")
        {
            manifestOption, outOption, preflightOption, stopAfterOption, printLadderOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var printLadder = parseResult.GetValue(printLadderOption);
            if (!string.IsNullOrWhiteSpace(printLadder))
                return PrintLadder(printLadder);

            var manifestFile = parseResult.GetValue(manifestOption);
            var outputDirectory = parseResult.GetValue(outOption);
            var preflightOnly = parseResult.GetValue(preflightOption);
            var stopAfter = Math.Max(0, parseResult.GetValue(stopAfterOption));

            if (manifestFile is null || outputDirectory is null)
            {
                await Console.Error.WriteLineAsync("error: --manifest and --out are required");
                return 2;
            }

            ContextLadderManifest manifest;
            IReadOnlyList<ContextLevelSpec> ladder;
            try
            {
                manifest = LoadAndValidate(manifestFile.FullName);
                ladder = ContextLadder.ForVersion(manifest.LadderVersion);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: context ladder manifest preflight failed: {ex.Message}");
                return 2;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(manifest.ModelName, out var adapter))
            {
                await Console.Error.WriteLineAsync($"error: evaluated model '{manifest.ModelName}' is not configured");
                return 2;
            }
            if (manifest.PromptVersion != ContextLadderPrompt.Version)
            {
                await Console.Error.WriteLineAsync(
                    $"error: prompt version drift (manifest {manifest.PromptVersion}; runtime {ContextLadderPrompt.Version})");
                return 2;
            }

            Console.Error.WriteLine($"Campaign: {manifest.CampaignId}");
            Console.Error.WriteLine($"Manifest SHA-256: {Sha256File(manifestFile.FullName)}");
            Console.Error.WriteLine($"Ladder: {manifest.LadderVersion} ({manifest.LadderSha256})");
            Console.Error.WriteLine(
                $"Assignments: {manifest.Assignments.Count}; model={manifest.ModelName}; " +
                $"repetitions={manifest.Repetitions}; applier=none (direct edit)");
            if (preflightOnly)
            {
                Console.Error.WriteLine("Context ladder preflight passed; no model call made.");
                return 0;
            }

            var root = Path.GetFullPath(outputDirectory.FullName);
            var traces = Path.Combine(root, "traces");
            var finalSources = Path.Combine(root, "final-sources");
            var ledgerPath = Path.Combine(root, "execution-ledger.jsonl");
            Directory.CreateDirectory(traces);
            Directory.CreateDirectory(finalSources);

            Dictionary<string, LadderExecutionRecord> completed;
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

            var contextBuilder = services.GetRequiredService<IContextBuilder>();
            var measurer = services.GetRequiredService<IRepairMeasurer>();
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
                        TraceSha256 = Sha256File(tracePath),
                        RunIds = store.Records.Select(r => r.RunId).ToList(),
                        EvaluatedModelCalls = 1,
                        CrossFileFiles = assignment.CrossFileDeclarations.Count,
                        CrossFileTruncated = assignment.CrossFileTruncated,
                        InputTokens = store.Records.Sum(r => r.InputTokens ?? 0),
                        OutputTokens = store.Records.Sum(r => r.OutputTokens ?? 0)
                    };
                    await AppendLedgerAsync(ledgerPath, execution, cancellationToken);
                    completed[assignment.AssignmentId] = execution;
                    executedThisInvocation++;

                    var outcome = record.VerifiedRepairLadder?.ToString()
                                  ?? record.ErrorStatus?.ToString()
                                  ?? "NoEdit";
                    Console.Error.WriteLine(
                        $"[{assignment.Order}/{manifest.Assignments.Count}] {assignment.ContextLevel} " +
                        $"{assignment.AntiPatternType} {assignment.SymbolName} -> {outcome}");
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex)
                {
                    await store.FlushAsync(cancellationToken);
                    await AppendLedgerAsync(ledgerPath, new LadderExecutionRecord
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
                        EvaluatedModelCalls = store.Records.Count,
                        CrossFileFiles = assignment.CrossFileDeclarations.Count,
                        CrossFileTruncated = assignment.CrossFileTruncated,
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
                $"Context ladder invocation complete: new={executedThisInvocation}, " +
                $"total={completed.Count}/{manifest.Assignments.Count}.");
            return 0;
        });

        return command;
    }

    /// <summary>
    /// Prints a ladder definition and its hash. The protocol section and the manifest's
    /// <c>ladder_sha256</c> are both derived from this rather than written by hand, which is what
    /// stops the prose and the executed definition drifting apart.
    /// </summary>
    private static int PrintLadder(string version)
    {
        IReadOnlyList<ContextLevelSpec> ladder;
        try { ladder = ContextLadder.ForVersion(version); }
        catch (ArgumentOutOfRangeException)
        {
            Console.Error.WriteLine(
                $"error: unknown ladder '{version}'; expected {ContextLadder.V1Version} or {ContextLadder.V2Version}");
            return 2;
        }

        Console.WriteLine($"ladder_version: {version}");
        Console.WriteLine($"ladder_sha256:  {ContextLadder.Sha256(ladder)}");
        Console.WriteLine();
        Console.WriteLine("| level | metrics | members | window | metadata | co-located | cross-file | caps |");
        Console.WriteLine("|---|---|---|---|---|---|---|---|");
        foreach (var spec in ladder)
        {
            var caps = spec.CrossFile == CrossFileScope.None
                ? "-"
                : $"{spec.MaxCrossFileFiles} files / {spec.MaxCrossFileChars} chars";
            Console.WriteLine(
                $"| {spec.Level} | {Mark(spec.IncludeMetrics)} | {Mark(spec.IncludeMemberSummary)} | "
                + $"{Mark(spec.IncludeSurroundingWindow)} | {Mark(spec.IncludeProjectMetadata)} | "
                + $"{Mark(spec.IncludeCoLocatedFindings)} | {spec.CrossFile} | {caps} |");
        }
        return 0;

        static string Mark(bool value) => value ? "yes" : "no";
    }

    /// <summary>
    /// Structural validation only: unlike the sealed grounding campaign this does not hard-code a
    /// target count, because the same instrument is pointed at the constructed corpus and at an
    /// industrial solution by swapping manifests. What must hold either way is that every target
    /// block carries all four levels exactly once, so the matched comparison is well formed.
    /// </summary>
    private static ContextLadderManifest LoadAndValidate(string path)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("manifest not found", path);
        var manifest = JsonSerializer.Deserialize<ContextLadderManifest>(File.ReadAllText(path), JsonOptions)
            ?? throw new InvalidDataException("manifest is empty or invalid");

        if (manifest.SchemaVersion != "2.0.0")
            throw new InvalidDataException("unsupported context ladder manifest schema");

        var ladder = ContextLadder.ForVersion(manifest.LadderVersion);
        var actual = ContextLadder.Sha256(ladder);
        if (!string.Equals(actual, manifest.LadderSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException(
                $"context ladder definition drift: manifest {manifest.LadderSha256}, runtime {actual}. "
                + "The frozen manifest was produced by a different definition of the levels.");

        if (!File.Exists(manifest.TargetSolution) ||
            !Path.GetExtension(manifest.TargetSolution).Equals(".sln", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("target solution not found", manifest.TargetSolution);
        if (!File.Exists(manifest.BaselineSource) || Sha256File(manifest.BaselineSource) != manifest.BaselineSha256)
            throw new InvalidDataException("frozen analyzer baseline is missing or changed");

        var count = manifest.Assignments.Count;
        if (count == 0) throw new InvalidDataException("manifest contains no assignments");
        if (manifest.Assignments.Select(a => a.AssignmentId).Distinct(StringComparer.Ordinal).Count() != count)
            throw new InvalidDataException("assignment IDs are not unique");
        if (!manifest.Assignments.Select(a => a.Order).Order().SequenceEqual(Enumerable.Range(1, count)))
            throw new InvalidDataException($"assignment order must be exactly 1..{count}");

        var allowed = new HashSet<ContextLevel>
        {
            ContextLevel.Minimal, ContextLevel.Structural, ContextLevel.Relational, ContextLevel.Full
        };
        foreach (var block in manifest.Assignments.GroupBy(a => a.BlockId, StringComparer.Ordinal))
        {
            if (block.Count() != 4 || !block.Select(a => a.ContextLevel).ToHashSet().SetEquals(allowed))
                throw new InvalidDataException(
                    $"block {block.Key} must contain each of the four context levels exactly once");
            if (block.Select(a => a.AntiPatternType).Distinct().Count() != 1)
                throw new InvalidDataException($"block {block.Key} mixes anti-pattern types");
        }

        if (manifest.Assignments.Count(a => a.ContextLevel == ContextLevel.Full) * 4 != count)
            throw new InvalidDataException("levels are not balanced across the campaign");

        foreach (var assignment in manifest.Assignments)
        {
            if (!File.Exists(assignment.FilePath) ||
                Sha256File(assignment.FilePath) != assignment.PristineSourceSha256)
                throw new InvalidDataException($"pristine source missing or changed: {assignment.AssignmentId}");
            if (assignment.TargetEndLine < assignment.Line)
                throw new InvalidDataException($"target end line precedes start: {assignment.AssignmentId}");

            // Cross-file payload is only meaningful where the level's specification asks for it.
            var spec = ContextLadder.For(ladder, assignment.ContextLevel);
            if (spec.CrossFile == CrossFileScope.None && assignment.CrossFileDeclarations.Count > 0)
                throw new InvalidDataException(
                    $"{assignment.AssignmentId} carries cross-file declarations at a level that does not use them");
            foreach (var declaration in assignment.CrossFileDeclarations)
            {
                if (Sha256Text(declaration.Source) != declaration.Sha256)
                    throw new InvalidDataException(
                        $"frozen cross-file source hash mismatch in {assignment.AssignmentId}: {declaration.RelativePath}");
            }
            if (assignment.CrossFileDeclarations.Count > spec.MaxCrossFileFiles && spec.MaxCrossFileFiles > 0)
                throw new InvalidDataException($"{assignment.AssignmentId} exceeds the frozen cross-file file cap");
        }

        return manifest;
    }

    private static Dictionary<string, LadderExecutionRecord> LoadCompleted(string ledgerPath, string campaignId)
    {
        var result = new Dictionary<string, LadderExecutionRecord>(StringComparer.Ordinal);
        if (!File.Exists(ledgerPath)) return result;
        foreach (var line in File.ReadLines(ledgerPath))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var record = JsonSerializer.Deserialize<LadderExecutionRecord>(line, LedgerJson)
                ?? throw new InvalidDataException("execution ledger contains an invalid row");
            if (record.CampaignId != campaignId)
                throw new InvalidDataException("execution ledger belongs to a different campaign");
            if (record.Completed && !result.TryAdd(record.AssignmentId, record))
                throw new InvalidDataException($"duplicate completed assignment: {record.AssignmentId}");
        }
        return result;
    }

    private static async Task AppendLedgerAsync(
        string ledgerPath, LadderExecutionRecord record, CancellationToken cancellationToken)
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

    private static string Sha256Text(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

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

    private sealed record LadderExecutionRecord
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
        public required int CrossFileFiles { get; init; }
        public required bool CrossFileTruncated { get; init; }
        public required int InputTokens { get; init; }
        public required int OutputTokens { get; init; }
        public string? Error { get; init; }
    }
}
