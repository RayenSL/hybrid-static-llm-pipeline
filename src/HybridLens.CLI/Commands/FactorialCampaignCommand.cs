using System.CommandLine;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Pipeline;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>Executes one frozen assignment at a time in manifest order, with crash-safe per-assignment traces.</summary>
public static class FactorialCampaignCommand
{
    private static readonly JsonSerializerOptions LedgerJson = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    public static Command Build(IServiceProvider services)
    {
        var manifestOption = new Option<FileInfo>("--manifest") { Required = true, Description = "Frozen campaign manifest." };
        var outOption = new Option<DirectoryInfo>("--out") { Required = true, Description = "Campaign output directory." };
        var dryRunOption = new Option<bool>("--dry-run")
        {
            Description = "Validate the manifest, resolve every target and print the plan. No model call is made."
        };
        var command = new Command("factorial-campaign",
            "Execute or safely resume a frozen randomized-block factorial campaign.")
        {
            manifestOption, outOption, dryRunOption
        };
        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var manifestFile = parseResult.GetValue(manifestOption)!;
            var outputDirectory = parseResult.GetValue(outOption)!;
            var dryRun = parseResult.GetValue(dryRunOption);
            if (!manifestFile.Exists)
            {
                await Console.Error.WriteLineAsync($"error: manifest not found: {manifestFile.FullName}");
                return 2;
            }

            FactorialCampaignManifest manifest;
            Dictionary<string, LoadedGeneratedTest> visibleByArtifact;
            try
            {
                manifest = await FactorialCampaignManifestStore.LoadAsync(
                    manifestFile.FullName, verifyFiles: true, cancellationToken);
                visibleByArtifact = await PreflightVisibleTestsAsync(manifest, cancellationToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: preflight failed before any model call: {ex.Message}");
                return 2;
            }

            if (dryRun)
            {
                // Preflight already validated the manifest, the target solution, the frozen baseline
                // hash and every pristine source hash. Report the plan and stop before any model call.
                Console.WriteLine($"manifest      : {manifestFile.FullName}");
                Console.WriteLine($"sha256        : {FactorialCampaignPlanner.Sha256File(manifestFile.FullName)}");
                Console.WriteLine($"campaign      : {manifest.CampaignId}"
                    + (manifest.Kind is null ? "" : $"  kind: {manifest.Kind}"));
                Console.WriteLine($"solution      : {manifest.TargetSolution}");
                Console.WriteLine($"model         : {manifest.ModelName}");
                Console.WriteLine($"design        : {string.Join(", ", FactorialCampaignPlanner.ExpectedSignatures(manifest))}");
                Console.WriteLine($"build args    : {(manifest.BuildArguments is { Count: > 0 } b ? string.Join(' ', b) : "(default)")}");
                Console.WriteLine($"assignments   : {manifest.Assignments.Count}"
                    + $" over {manifest.Assignments.Select(a => a.SymbolName).Distinct(StringComparer.Ordinal).Count()} target(s)"
                    + $" x {manifest.Repetitions} repetition(s)");
                Console.WriteLine($"visible tests : {manifest.Assignments.Count(a => a.VisibleTestsEnabled)} assignment(s)");
                foreach (var target in manifest.Assignments
                             .GroupBy(a => a.SymbolName, StringComparer.Ordinal)
                             .OrderBy(g => g.Key, StringComparer.Ordinal))
                {
                    var first = target.First();
                    Console.WriteLine($"  {target.Key,-56} {first.AntiPatternType,-12}"
                        + $" lines {first.Line}-{first.TargetEndLine}  {target.Count()} assignment(s)");
                }
                Console.WriteLine("dry run: manifest, solution, baseline and all pristine sources verified");
                return 0;
            }

            var adapters = services.GetRequiredService<IReadOnlyDictionary<string, ILlmAdapter>>();
            if (!adapters.TryGetValue(manifest.ModelName, out var adapter))
            {
                await Console.Error.WriteLineAsync($"error: frozen model '{manifest.ModelName}' is not configured");
                return 2;
            }

            var root = Path.GetFullPath(outputDirectory.FullName);
            var traces = Path.Combine(root, "traces");
            var trajectories = Path.Combine(root, "trajectories");
            var finalSources = Path.Combine(root, "final-sources");
            var ledgerPath = Path.Combine(root, "execution-ledger.jsonl");
            Directory.CreateDirectory(traces);
            Directory.CreateDirectory(trajectories);
            Directory.CreateDirectory(finalSources);

            var completed = LoadCompleted(ledgerPath, manifest.CampaignId);
            foreach (var prior in completed.Values)
                if (!File.Exists(prior.TraceFile))
                {
                    await Console.Error.WriteLineAsync(
                        $"error: completed assignment {prior.AssignmentId} has no trace: {prior.TraceFile}");
                    return 2;
                }

            var contextBuilder = services.GetRequiredService<IContextBuilder>();
            var measurer = services.GetRequiredService<IRepairMeasurer>();
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

            Console.Error.WriteLine($"Campaign: {manifest.CampaignId}"
                + (manifest.Kind is null ? "" : $"  kind: {manifest.Kind}"));
            if (buildArguments is not null)
                Console.Error.WriteLine($"Build arguments: {string.Join(' ', buildArguments)}");
            Console.Error.WriteLine("Working copy omits: "
                + string.Join(' ', skipDirectories ?? FactorialSingleShotRunner.DefaultSkipDirs));
            Console.Error.WriteLine(
                $"Design: {string.Join(", ", FactorialCampaignPlanner.ExpectedSignatures(manifest))}");
            Console.Error.WriteLine($"Manifest SHA-256: {FactorialCampaignPlanner.Sha256File(manifestFile.FullName)}");
            Console.Error.WriteLine($"Assignments: {manifest.Assignments.Count}; already completed: {completed.Count}");

            foreach (var assignment in manifest.Assignments.OrderBy(a => a.Order))
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (completed.ContainsKey(assignment.AssignmentId)) continue;
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
                            Console.Error,
                            cancellationToken,
                            sweepFiles: [assignment.FilePath],
                            groundingByFile: grounding,
                            visibleTestsByFile: visibleByFile,
                            visibleTestsEnabled: assignment.VisibleTestsEnabled,
                            finalArtifactDirectory: finalSources,
                            runNumberOffset: assignment.RunNumber - 1);
                    }

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
                    await AppendLedgerAsync(ledgerPath, execution, cancellationToken);
                    completed[assignment.AssignmentId] = execution;
                    Console.Error.WriteLine(
                        $"[{assignment.Order}/{manifest.Assignments.Count}] {assignment.AssignmentId}: " +
                        $"grounded={assignment.GroundingEnabled}, control={assignment.ControlStructure}, " +
                        $"tests={assignment.VisibleTestsEnabled} complete");
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex)
                {
                    await AppendLedgerAsync(ledgerPath, new FactorialCampaignExecutionRecord
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
                    await Console.Error.WriteLineAsync($"error: assignment {assignment.AssignmentId} failed: {ex.Message}");
                    return 1;
                }
            }

            Console.Error.WriteLine("Factorial campaign complete. Freeze the output directory before private evaluation.");
            return 0;
        });
        return command;
    }

    private static async Task<Dictionary<string, LoadedGeneratedTest>> PreflightVisibleTestsAsync(
        FactorialCampaignManifest manifest,
        CancellationToken cancellationToken)
    {
        var result = new Dictionary<string, LoadedGeneratedTest>(StringComparer.OrdinalIgnoreCase);
        foreach (var assignment in manifest.Assignments.Where(a => a.VisibleTestArtifactRef is not null))
        {
            var path = Path.GetFullPath(assignment.VisibleTestArtifactRef!);
            if (result.ContainsKey(path)) continue;
            var loaded = await GeneratedTestArtifactLoader.LoadAdmittedAsync(path, cancellationToken);
            if (!Path.GetFullPath(loaded.Artifact.ArtifactRef).Equals(path, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible-test artifact_ref does not identify its manifest file: {path}");
            if (!Path.GetFullPath(loaded.Artifact.SourceFile)
                    .Equals(Path.GetFullPath(assignment.FilePath), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible test is mapped to a different source file: {path}");
            if (!string.Equals(loaded.Artifact.TestSha256, assignment.VisibleTestSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible-test hash changed after manifest freeze: {path}");
            if (!string.Equals(loaded.Artifact.SourceSha256, assignment.PristineSourceSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"visible test is bound to a different source revision: {path}");
            if (!string.Equals(loaded.Artifact.TargetSymbolName, assignment.SymbolName, StringComparison.Ordinal) ||
                loaded.Artifact.TargetStartLine != assignment.Line ||
                loaded.Artifact.TargetEndLine != assignment.TargetEndLine)
                throw new InvalidDataException($"visible test is bound to a different target declaration: {path}");
            result[path] = loaded;
        }
        return result;
    }

    private static Dictionary<string, FactorialCampaignExecutionRecord> LoadCompleted(
        string ledgerPath,
        string campaignId)
    {
        var result = new Dictionary<string, FactorialCampaignExecutionRecord>(StringComparer.Ordinal);
        if (!File.Exists(ledgerPath)) return result;
        foreach (var line in File.ReadLines(ledgerPath))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var record = JsonSerializer.Deserialize<FactorialCampaignExecutionRecord>(line, LedgerJson)
                ?? throw new InvalidDataException("execution ledger contains an invalid row");
            if (record.CampaignId != campaignId)
                throw new InvalidDataException("execution ledger belongs to a different campaign");
            if (record.Completed)
            {
                if (!result.TryAdd(record.AssignmentId, record))
                    throw new InvalidDataException($"execution ledger contains duplicate completion: {record.AssignmentId}");
            }
        }
        return result;
    }

    private static async Task AppendLedgerAsync(
        string ledgerPath,
        FactorialCampaignExecutionRecord record,
        CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(ledgerPath)!);
        var line = JsonSerializer.Serialize(record, LedgerJson) + Environment.NewLine;
        await File.AppendAllTextAsync(ledgerPath, line, new UTF8Encoding(false), cancellationToken);
    }

    private sealed class RecordingRunStore(string tracePath) : IRunStore
    {
        private readonly JsonlRunStore _inner = new(tracePath);
        public List<string> RunIds { get; } = [];

        public async Task AppendAsync(RunRecord record, CancellationToken cancellationToken = default)
        {
            await _inner.AppendAsync(record, cancellationToken);
            RunIds.Add(record.RunId);
        }

        public ValueTask DisposeAsync() => _inner.DisposeAsync();
    }
}
