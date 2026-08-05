using System.Diagnostics;
using System.Text.Json;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Executes one genuinely independent single-shot direct-edit repair. Exactly one evaluated-model call is
/// made; build and visible-test results are measured only after the response and are never fed back.
/// </summary>
public sealed class FactorialSingleShotRunner(
    ILlmAdapter adapter,
    string modelName,
    IRepairMeasurer measurer,
    string solutionPath,
    int buildTimeoutSeconds,
    Func<string, int, CancellationToken, Task<(bool Ok, string Output)>>? build = null,
    Func<GeneratedTestSource, string, int, CancellationToken, Task<GeneratedTestExecutionResult>>? executeVisibleTest = null,
    IReadOnlyList<string>? workingCopySkipDirectories = null)
{
    public static readonly string[] DefaultSkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];

    private readonly string[] _skipDirs = workingCopySkipDirectories is { Count: > 0 } declared
        ? [.. declared] : DefaultSkipDirs;
    private readonly Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> _build
        = build ?? DotnetBuilder.BuildAsync;
    private readonly Func<GeneratedTestSource, string, int, CancellationToken, Task<GeneratedTestExecutionResult>> _executeVisibleTest
        = executeVisibleTest ?? GeneratedTestAdmissionRunner.ExecuteOnceAsync;

    public async Task<RunRecord> RunAttemptAsync(
        KnownInstance instance,
        int runNumber,
        bool grounded,
        string? groundingBlock,
        bool visibleTestsEnabled,
        LoadedGeneratedTest? visibleTest,
        string finalArtifactDirectory,
        CancellationToken cancellationToken)
    {
        if (grounded && string.IsNullOrWhiteSpace(groundingBlock))
            throw new ArgumentException("grounded single-shot requires a finding block", nameof(groundingBlock));
        if (!visibleTestsEnabled && visibleTest is not null)
            throw new ArgumentException("a visible test cannot be supplied to a test-disabled cell", nameof(visibleTest));
        var targetDescriptor = BlindedTargetDescriptor.Create(
            instance.SymbolName, instance.Line, instance.EndLine);
        if (visibleTest is not null)
        {
            GeneratedTestArtifactLoader.VerifyUnchanged(visibleTest);
            if (!Path.GetFullPath(visibleTest.Artifact.SourceFile)
                    .Equals(Path.GetFullPath(instance.FilePath), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("visible test was generated for a different source file");
            if (!string.Equals(visibleTest.Artifact.TargetSymbolName, targetDescriptor.SymbolName, StringComparison.Ordinal) ||
                visibleTest.Artifact.TargetStartLine != targetDescriptor.StartLine ||
                visibleTest.Artifact.TargetEndLine != targetDescriptor.EndLine)
                throw new InvalidDataException("visible test was generated for a different target declaration");
        }

        var corpusRoot = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-single-shot-{Guid.NewGuid():N}");
        var workingSln = Path.Combine(workingRoot, Path.GetFileName(solutionPath));
        var sourceFull = Path.GetFullPath(instance.FilePath);
        var relative = Path.GetRelativePath(corpusRoot, sourceFull);
        if (relative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(relative))
            throw new ArgumentException("instance source is outside the corpus root", nameof(instance));
        var workingTarget = Path.Combine(workingRoot, relative);
        var original = await File.ReadAllTextAsync(sourceFull, cancellationToken);
        if (visibleTest is not null)
        {
            var sourceHash = MaterializedSourceArtifactWriter.Sha256(original);
            if (!string.Equals(sourceHash, visibleTest.Artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(
                    "visible test was generated from a different pristine source revision");
        }
        var architecture = grounded ? "grounded_single_shot" : "ungrounded_single_shot";
        var systemPrompt = grounded
            ? FactorialSingleShotPrompt.GroundedSystemPrompt
            : FactorialSingleShotPrompt.UngroundedSystemPrompt;
        var visiblePrompt = visibleTest is null ? null : new LoadedVisibleTestPrompt(
            visibleTest.Source.TestName,
            visibleTest.Source.UsingDirectives,
            visibleTest.Source.TestBody,
            visibleTest.Artifact.TestSha256!);
        var userPrompt = FactorialSingleShotPrompt.BuildUserPrompt(
            relative.Replace('\\', '/'), original, targetDescriptor,
            grounded ? groundingBlock : null, visiblePrompt);

        CopyTree(corpusRoot, workingRoot);
        var stopwatch = Stopwatch.StartNew();
        LlmResponse? response = null;
        ParsedRepair? parsed = null;
        ErrorStatus? error = null;
        string? errorMessage = null;
        bool? built = null;
        string? buildOutputTail = null;
        bool? visiblePassed = null;
        var testDuration = 0d;
        var testAttempts = 0;
        IReadOnlyDictionary<string, double>? remeasured = null;
        VerifiedRepairOutcome? ladder = null;
        string? materializedRef = null;
        string? materializedHash = null;
        try
        {
            try
            {
                response = await adapter.CompleteAsync(new LlmRequest
                {
                    SystemPrompt = systemPrompt,
                    UserPrompt = userPrompt,
                    PromptVersion = FactorialSingleShotPrompt.Version
                }, cancellationToken);
                parsed = Parse(response.Content);
                if (parsed is null)
                {
                    error = ErrorStatus.ParseFailure;
                    errorMessage = "single-shot output did not match the required JSON contract";
                }
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                error = ErrorStatus.ApiFailure;
                errorMessage = ex.Message;
            }

            if (parsed is not null)
            {
                await File.WriteAllTextAsync(workingTarget, parsed.EditedFile, cancellationToken);
                var buildResult = await _build(workingSln, buildTimeoutSeconds, cancellationToken);
                built = buildResult.Ok;
                // A bare false cannot tell a broken repair from a broken harness; keep the evidence.
                buildOutputTail = buildResult.Ok ? null : Tail(buildResult.Output, 4000);
                if (built == true && visibleTest is not null)
                {
                    var originalProject = visibleTest.Artifact.ProjectFile;
                    var projectRelative = Path.GetRelativePath(corpusRoot, originalProject);
                    if (projectRelative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(projectRelative))
                        throw new InvalidDataException("visible-test production project is outside the corpus root");
                    testAttempts = 1;
                    var executed = await _executeVisibleTest(
                        visibleTest.Source,
                        Path.Combine(workingRoot, projectRelative),
                        buildTimeoutSeconds,
                        cancellationToken);
                    visiblePassed = executed.BuildPassed && executed.TestPassed;
                    testDuration = executed.DurationMs;
                    GeneratedTestArtifactLoader.VerifyUnchanged(visibleTest);
                }

                if (built == true)
                {
                    var measured = await measurer.RemeasureAsync(
                        instance.Type, workingTarget, instance.SymbolName, cancellationToken);
                    ladder = measured.StillTriggers
                        ? VerifiedRepairOutcome.BuildsUnresolved
                        : VerifiedRepairOutcome.Resolved;
                    remeasured = measured.StillTriggers ? measured.Metrics : null;
                }
                else
                {
                    ladder = VerifiedRepairOutcome.BuildFails;
                }

                var artifact = new MaterializedSourceArtifact
                {
                    ArtifactId = Guid.NewGuid().ToString("N"),
                    Timestamp = DateTimeOffset.UtcNow,
                    Architecture = architecture,
                    GroundingEnabled = grounded,
                    ControlStructure = "single_shot",
                    VisibleTestsEnabled = visibleTestsEnabled,
                    VisibleTestAvailable = visibleTest is not null,
                    RunNumber = runNumber,
                    RelativeFile = relative.Replace('\\', '/'),
                    SourceSha256 = MaterializedSourceArtifactWriter.Sha256(parsed.EditedFile),
                    FinalSource = parsed.EditedFile,
                    VisibleTestArtifactRef = visibleTest?.Artifact.ArtifactRef,
                    VisibleTestSha256 = visibleTest?.Artifact.TestSha256,
                    BuildPassed = built,
                    VisibleTestPassed = visiblePassed
                };
                materializedRef = await MaterializedSourceArtifactWriter.WriteAsync(
                    finalArtifactDirectory, artifact, cancellationToken);
                materializedHash = artifact.SourceSha256;
            }
        }
        finally
        {
            stopwatch.Stop();
            TryDeleteTree(workingRoot);
        }

        var recovered = grounded || (parsed?.Findings.Any(f => Matches(f, instance)) ?? false);
        return new RunRecord
        {
            RunId = Guid.NewGuid().ToString("N"),
            Timestamp = DateTimeOffset.UtcNow,
            RunNumber = runNumber,
            AntiPatternType = instance.Type,
            FilePath = instance.FilePath,
            SymbolName = instance.SymbolName,
            Line = instance.Line,
            Severity = instance.Severity,
            Snippet = instance.Snippet,
            Metrics = null,
            ContextLevel = grounded ? ContextLevel.Structural : ContextLevel.Minimal,
            ModelName = modelName,
            PromptVersion = FactorialSingleShotPrompt.Version,
            Architecture = architecture,
            GroundingEnabled = grounded,
            ControlStructure = "single_shot",
            VisibleTestsEnabled = visibleTestsEnabled,
            VisibleTestAvailable = visibleTest is not null,
            VisibleTestArtifactRef = visibleTest?.Artifact.ArtifactRef,
            VisibleTestSha256 = visibleTest?.Artifact.TestSha256,
            VisibleTestPassed = visiblePassed,
            LlmCallCount = 1,
            BuildAttemptCount = parsed is null ? 0 : 1,
            TestAttemptCount = testAttempts,
            TestDurationMs = testDuration,
            MaterializedSourceRef = materializedRef,
            MaterializedSourceSha256 = materializedHash,
            RawSystemPrompt = systemPrompt,
            RawUserPrompt = userPrompt,
            RawLlmOutput = response?.Content,
            InputTokens = response?.InputTokens,
            OutputTokens = response?.OutputTokens,
            DurationMs = stopwatch.Elapsed.TotalMilliseconds,
            RepairApplicable = parsed is not null,
            BuildPassed = built,
            BuildOutputTail = buildOutputTail,
            RemeasuredMetrics = remeasured,
            VerifiedRepairLadder = ladder,
            VerifiedRepairSuccess = ladder == VerifiedRepairOutcome.Resolved,
            AgenticRecovered = recovered,
            ParseStatus = parsed is not null ? ParseStatus.Ok : response is null ? ParseStatus.NotAttempted : ParseStatus.Failed,
            ErrorStatus = error,
            ErrorMessage = errorMessage
        };
    }

    private sealed record ParsedFinding(string? AntiPattern, string? Symbol, int Line);
    private sealed record ParsedRepair(string EditedFile, IReadOnlyList<ParsedFinding> Findings);

    private static ParsedRepair? Parse(string raw)
    {
        try
        {
            var json = raw.Trim();
            if (json.StartsWith("```", StringComparison.Ordinal))
            {
                json = string.Join('\n', json.Split('\n').Skip(1));
                var fence = json.LastIndexOf("```", StringComparison.Ordinal);
                if (fence >= 0) json = json[..fence].Trim();
            }
            using var document = JsonDocument.Parse(json);
            var root = document.RootElement;
            var edited = root.TryGetProperty("edited_file", out var e) ? e.GetString() : null;
            if (string.IsNullOrWhiteSpace(edited)) return null;
            var findings = new List<ParsedFinding>();
            if (root.TryGetProperty("findings", out var fs) && fs.ValueKind == JsonValueKind.Array)
                foreach (var f in fs.EnumerateArray())
                    findings.Add(new ParsedFinding(
                        f.TryGetProperty("anti_pattern", out var a) ? a.GetString() : null,
                        f.TryGetProperty("symbol", out var s) ? s.GetString() : null,
                        f.TryGetProperty("line", out var l) && l.TryGetInt32(out var line) ? line : 0));
            return new ParsedRepair(edited, findings);
        }
        catch { return null; }
    }

    private static bool Matches(ParsedFinding finding, KnownInstance instance)
    {
        var lineMatch = finding.Line >= instance.Line && finding.Line <= instance.EndLine;
        var reported = SimpleName(finding.Symbol);
        var expected = SimpleName(instance.SymbolName);
        var symbolMatch = reported.Length > 0 && expected.Length > 0 &&
                          (reported.Contains(expected, StringComparison.OrdinalIgnoreCase) ||
                           expected.Contains(reported, StringComparison.OrdinalIgnoreCase));
        return lineMatch || symbolMatch;
    }

    private static string SimpleName(string? symbol)
    {
        if (string.IsNullOrWhiteSpace(symbol)) return string.Empty;
        var value = symbol.Trim();
        var paren = value.IndexOf('(');
        if (paren >= 0) value = value[..paren];
        var dot = value.LastIndexOf('.');
        return dot >= 0 && dot < value.Length - 1 ? value[(dot + 1)..] : value;
    }

    private static string Tail(string value, int maxChars) =>
        string.IsNullOrEmpty(value) || value.Length <= maxChars ? value : value[^maxChars..];

    private void CopyTree(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var relative = Path.GetRelativePath(source, file);
            if (relative.Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries)
                .Any(part => _skipDirs.Contains(part, StringComparer.OrdinalIgnoreCase))) continue;
            var target = Path.Combine(destination, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { }
    }
}
