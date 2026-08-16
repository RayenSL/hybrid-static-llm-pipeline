using System.CommandLine;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.ContextBuilder;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;
using HybridLens.Pipeline;
using HybridLens.StaticAnalysis;
using HybridLens.StaticAnalysis.Workspace;
using Microsoft.CodeAnalysis;
using Microsoft.Extensions.DependencyInjection;

namespace HybridLens.CLI.Commands;

/// <summary>
/// Freezes the complete randomised assignment schedule for the direct-edit context ladder, together
/// with the cross-file payload its Full rung supplies.
///
/// Resolution happens here rather than at prompt time for three reasons: it needs a Roslyn
/// compilation and <see cref="HybridLens.ContextBuilder"/> deliberately has none; a frozen payload
/// makes every prompt reproducible from the manifest alone; and hashing it proves the supplied
/// source predates every repair.
///
/// The same command serves the constructed corpus and an industrial solution — the venue is the
/// <c>--target</c> solution, not a code path.
/// </summary>
public static class ContextLadderManifestCommand
{
    private static readonly JsonSerializerOptions ManifestJson = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    public static Command Build(IServiceProvider services)
    {
        var fromOption = new Option<FileInfo>("--from")
        { Required = true, Description = "Frozen analyser JSON output (the dry-run baseline)." };
        var targetOption = new Option<FileInfo>("--target")
        { Required = true, Description = "Pristine solution (.sln)." };
        var modelOption = new Option<string>("--model")
        { Required = true, Description = "Frozen evaluated-model key." };
        var revisionOption = new Option<string>("--code-revision")
        { Required = true, Description = "Frozen VCS revision of the implementation used." };
        var seedOption = new Option<int>("--seed")
        { Required = true, Description = "Fixed randomisation seed." };
        var outOption = new Option<FileInfo>("--out")
        { Required = true, Description = "Output manifest JSON path. An existing file is never overwritten." };
        var ladderOption = new Option<string>("--ladder")
        { Description = $"Ladder version (default: {ContextLadder.V2Version})." };
        var runsOption = new Option<int>("--runs")
        { Description = "Repetitions per target (default: 3)." };
        var timeoutOption = new Option<int>("--build-timeout")
        { Description = "Build timeout seconds (default: 180)." };
        var admittedOption = new Option<FileInfo?>("--admitted")
        {
            Description = "Optional JSON array of {file, symbol, line} restricting the baseline to "
                        + "hand-confirmed targets. Without it every detector finding becomes a target."
        };
        var metadataOption = new Option<string[]>("--metadata")
        {
            Description = "Frozen project metadata as Key=Value, repeatable. Supplied to levels whose "
                        + "specification asks for it.",
            AllowMultipleArgumentsPerToken = false
        };

        var command = new Command("context-ladder-manifest",
            "Freeze a randomised four-level context ladder schedule, resolving cross-file context once.")
        {
            fromOption, targetOption, modelOption, revisionOption, seedOption, outOption,
            ladderOption, runsOption, timeoutOption, admittedOption, metadataOption
        };

        command.SetAction(async (parseResult, cancellationToken) =>
        {
            var from = parseResult.GetValue(fromOption)!;
            var target = parseResult.GetValue(targetOption)!;
            var model = parseResult.GetValue(modelOption)!;
            var revision = parseResult.GetValue(revisionOption)!;
            var seed = parseResult.GetValue(seedOption);
            var output = parseResult.GetValue(outOption)!;
            var ladderVersion = parseResult.GetValue(ladderOption) ?? ContextLadder.V2Version;
            var runs = parseResult.GetValue(runsOption);
            var timeout = parseResult.GetValue(timeoutOption);
            var admittedFile = parseResult.GetValue(admittedOption);
            var metadataPairs = parseResult.GetValue(metadataOption) ?? [];
            if (runs < 1) runs = 3;
            if (timeout < 1) timeout = 180;

            if (!from.Exists || !target.Exists)
            {
                await Console.Error.WriteLineAsync("error: --from and --target must exist");
                return 2;
            }
            if (output.Exists)
            {
                await Console.Error.WriteLineAsync($"error: refusing to overwrite an existing manifest: {output.FullName}");
                return 2;
            }

            IReadOnlyList<ContextLevelSpec> ladder;
            try { ladder = ContextLadder.ForVersion(ladderVersion); }
            catch (ArgumentOutOfRangeException)
            {
                await Console.Error.WriteLineAsync($"error: unknown ladder version '{ladderVersion}'");
                return 2;
            }

            var metadata = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var pair in metadataPairs)
            {
                var split = pair.IndexOf('=');
                if (split <= 0)
                {
                    await Console.Error.WriteLineAsync($"error: --metadata must be Key=Value: '{pair}'");
                    return 2;
                }
                metadata[pair[..split]] = pair[(split + 1)..];
            }

            try
            {
                // The analyser records repository-relative paths, so they resolve against the
                // solution directory rather than the process working directory.
                var solutionRoot = Path.GetDirectoryName(Path.GetFullPath(target.FullName))!;
                var targets = LoadTargets(from.FullName, admittedFile?.FullName, solutionRoot);
                if (targets.Count == 0)
                    throw new InvalidDataException("baseline contains no targets after admission filtering");

                var fullSpec = ContextLadder.For(ladder, ContextLevel.Full);
                // The same workspace configuration that produced the baseline, so the set of loaded
                // projects during resolution matches the set during detection.
                var workspaceConfig = services.GetRequiredService<WorkspaceConfig>();
                var resolutions = fullSpec.CrossFile == CrossFileScope.None
                    ? targets.ToDictionary(t => t.Key, _ => CrossFileResolution.Empty, StringComparer.Ordinal)
                    : await ResolveCrossFileAsync(
                        target.FullName, targets, fullSpec, workspaceConfig, cancellationToken);

                var manifest = Plan(
                    targets, resolutions, ladder, ladderVersion, target.FullName, from.FullName,
                    model, revision, runs, timeout, seed, metadata);

                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output.FullName))!);
                await using (var stream = new FileStream(
                    output.FullName, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
                {
                    await JsonSerializer.SerializeAsync(stream, manifest, ManifestJson, cancellationToken);
                }

                var truncated = manifest.Assignments.Count(a => a.CrossFileTruncated);
                var withContext = manifest.Assignments.Count(a => a.CrossFileDeclarations.Count > 0);
                Console.Error.WriteLine($"Manifest: {Path.GetFullPath(output.FullName)}");
                Console.Error.WriteLine($"Campaign: {manifest.CampaignId}");
                Console.Error.WriteLine($"Ladder:   {ladderVersion} ({manifest.LadderSha256})");
                Console.Error.WriteLine(
                    $"Assignments: {manifest.Assignments.Count} "
                    + $"({targets.Count} targets x {runs} repetitions x 4 levels)");
                Console.Error.WriteLine(
                    $"Cross-file: {withContext} assignments carry declarations; {truncated} were capped");
                return 0;
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                await Console.Error.WriteLineAsync($"error: {ex.Message}");
                return 2;
            }
        });

        return command;
    }

    private sealed record LadderTarget(
        string Key, AntiPatternType Type, Severity Severity, string FilePath, string SymbolName,
        int Line, int EndLine, string? Snippet, Dictionary<string, double> Metrics);

    /// <summary>
    /// Reads the analyser's frozen JSON output. When an admitted list is supplied the baseline is
    /// restricted to it, which is how a hand-confirmed target set (industrial probe) or a single
    /// anti-pattern stratum (corpus Obsolete API) is selected without re-running detection.
    /// </summary>
    private static List<LadderTarget> LoadTargets(
        string baselinePath, string? admittedPath, string solutionRoot)
    {
        string Resolve(string path) => Path.IsPathRooted(path)
            ? Path.GetFullPath(path)
            : Path.GetFullPath(Path.Combine(solutionRoot, path));

        using var document = JsonDocument.Parse(File.ReadAllText(baselinePath));
        var findings = document.RootElement.TryGetProperty("findings", out var array)
            ? array
            : throw new InvalidDataException("baseline has no 'findings' array");

        HashSet<string>? admitted = null;
        if (admittedPath is not null)
        {
            using var admittedDoc = JsonDocument.Parse(File.ReadAllText(admittedPath));
            admitted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var entry in admittedDoc.RootElement.EnumerateArray())
            {
                var file = entry.GetProperty("file").GetString()!;
                var symbol = entry.GetProperty("symbol").GetString()!;
                admitted.Add($"{Resolve(file)}::{symbol}");
            }
        }

        var targets = new List<LadderTarget>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var finding in findings.EnumerateArray())
        {
            var type = NormaliseType(finding.GetProperty("type").GetString());
            if (type is null) continue;
            var file = finding.GetProperty("filePath").GetString();
            var symbol = finding.GetProperty("symbolName").GetString();
            if (file is null || symbol is null) continue;

            var full = Resolve(file);
            if (admitted is not null && !admitted.Contains($"{full}::{symbol}")) continue;

            var line = finding.TryGetProperty("line", out var l) ? l.GetInt32() : 0;
            var snippet = finding.TryGetProperty("snippet", out var s) ? s.GetString() : null;
            var severity = finding.TryGetProperty("severity", out var sev)
                ? sev.GetString()?.ToLowerInvariant() switch
                {
                    "critical" => Severity.Critical,
                    "warning" => Severity.Warning,
                    _ => Severity.Info
                }
                : Severity.Warning;

            var metrics = new Dictionary<string, double>(StringComparer.Ordinal);
            if (finding.TryGetProperty("metrics", out var m) && m.ValueKind == JsonValueKind.Object)
                foreach (var metric in m.EnumerateObject())
                    if (metric.Value.TryGetDouble(out var value)) metrics[metric.Name] = value;

            // One target per class is the probe's independence rule and the corpus satisfies it by
            // construction; deduplicating on file+symbol keeps a repeated detection from becoming
            // two matched blocks over the same declaration.
            var key = $"{full}::{symbol}::{line}";
            if (!seen.Add(key)) continue;

            var known = KnownInstance.Create(type.Value, full, symbol, line, severity, snippet);
            targets.Add(new LadderTarget(
                key, type.Value, severity, full, symbol, line, known.EndLine, snippet, metrics));
        }

        return targets;
    }

    private static AntiPatternType? NormaliseType(string? raw) => raw?.ToLowerInvariant() switch
    {
        "godclass" or "god_class" => AntiPatternType.GodClass,
        "longmethod" or "long_method" => AntiPatternType.LongMethod,
        "obsoleteapiusage" or "obsolete_api_usage" or "obsoleteapi" => AntiPatternType.ObsoleteApiUsage,
        _ => null
    };

    /// <summary>
    /// Loads the solution once and resolves every target's cross-file payload against it. Loading a
    /// large solution is the expensive step, so it happens once for the whole manifest rather than
    /// per assignment.
    /// </summary>
    private static async Task<Dictionary<string, CrossFileResolution>> ResolveCrossFileAsync(
        string solutionPath, IReadOnlyList<LadderTarget> targets, ContextLevelSpec fullSpec,
        WorkspaceConfig workspaceConfig, CancellationToken cancellationToken)
    {
        var solutionRoot = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        using var loader = new WorkspaceLoader(workspaceConfig);
        var compilations = await loader.LoadAsync(solutionPath, cancellationToken);
        if (compilations.Count == 0)
            throw new InvalidDataException("no projects loaded from the target solution");

        var byFile = new Dictionary<string, Compilation>(StringComparer.OrdinalIgnoreCase);
        foreach (var compilation in compilations)
            foreach (var tree in compilation.SyntaxTrees)
                if (!string.IsNullOrEmpty(tree.FilePath))
                    byFile.TryAdd(Path.GetFullPath(tree.FilePath), compilation);

        var result = new Dictionary<string, CrossFileResolution>(StringComparer.Ordinal);
        foreach (var target in targets)
        {
            if (!byFile.TryGetValue(Path.GetFullPath(target.FilePath), out var compilation))
            {
                // A target whose file is in no loaded project cannot be resolved. Recording an empty
                // payload rather than failing keeps a partially-loading industrial solution usable,
                // and the campaign's own validation still refuses a manifest that is internally
                // inconsistent.
                result[target.Key] = CrossFileResolution.Empty;
                continue;
            }

            result[target.Key] = CrossFileDeclarationResolver.Resolve(
                compilation, target.FilePath, target.Line, target.EndLine, fullSpec, solutionRoot);
        }

        return result;
    }

    /// <summary>
    /// Builds the schedule. Target blocks are shuffled, and the four levels are shuffled within each
    /// block, both from the recorded seed — so the order in which a level is attempted cannot be
    /// confounded with the level itself.
    /// </summary>
    private static ContextLadderManifest Plan(
        IReadOnlyList<LadderTarget> targets,
        IReadOnlyDictionary<string, CrossFileResolution> resolutions,
        IReadOnlyList<ContextLevelSpec> ladder,
        string ladderVersion,
        string solutionPath,
        string baselinePath,
        string model,
        string revision,
        int runs,
        int timeout,
        int seed,
        Dictionary<string, string> metadata)
    {
        var random = new Random(seed);
        var levels = new[]
        {
            ContextLevel.Minimal, ContextLevel.Structural, ContextLevel.Relational, ContextLevel.Full
        };

        var blocks = new List<(LadderTarget Target, int Run)>();
        foreach (var target in targets)
            for (var run = 1; run <= runs; run++)
                blocks.Add((target, run));
        Shuffle(blocks, random);

        var assignments = new List<LadderAssignment>();
        var order = 1;
        foreach (var (target, run) in blocks)
        {
            var blockLevels = levels.ToList();
            Shuffle(blockLevels, random);
            var blockId = Hash($"{target.Key}::run{run}")[..16];
            var resolution = resolutions.TryGetValue(target.Key, out var r) ? r : CrossFileResolution.Empty;

            foreach (var level in blockLevels)
            {
                var spec = ContextLadder.For(ladder, level);
                var carriesCrossFile = spec.CrossFile != CrossFileScope.None;

                assignments.Add(new LadderAssignment
                {
                    Order = order,
                    AssignmentId = Hash($"{blockId}::{level}")[..24],
                    BlockId = blockId,
                    RunNumber = run,
                    ContextLevel = level,
                    AntiPatternType = target.Type,
                    Severity = target.Severity,
                    FilePath = target.FilePath,
                    SymbolName = target.SymbolName,
                    Line = target.Line,
                    TargetEndLine = target.EndLine,
                    Snippet = target.Snippet,
                    Metrics = new Dictionary<string, double>(target.Metrics, StringComparer.Ordinal),
                    ExpectedQualityAttributes = [.. QualityAttributeMap.ForType(target.Type)],
                    PristineSourceSha256 = Sha256File(target.FilePath),
                    ProjectMetadata = spec.IncludeProjectMetadata
                        ? new Dictionary<string, string>(metadata, StringComparer.Ordinal)
                        : new Dictionary<string, string>(StringComparer.Ordinal),
                    CrossFileDeclarations = carriesCrossFile ? [.. resolution.Included] : [],
                    CrossFileDropped = carriesCrossFile ? [.. resolution.Dropped] : []
                });
                order++;
            }
        }

        return new ContextLadderManifest
        {
            SchemaVersion = "2.0.0",
            CampaignId = Hash($"{model}::{revision}::{seed}::{targets.Count}::{runs}::{ladderVersion}")[..24],
            ModelName = model,
            TargetSolution = Path.GetFullPath(solutionPath),
            BaselineSource = Path.GetFullPath(baselinePath),
            BaselineSha256 = Sha256File(baselinePath),
            CodeRevision = revision,
            PromptVersion = ContextLadderPrompt.Version,
            LadderVersion = ladderVersion,
            LadderSha256 = ContextLadder.Sha256(ladder),
            Repetitions = runs,
            RandomizationSeed = seed,
            BuildTimeoutSeconds = timeout,
            Assignments = assignments
        };
    }

    private static void Shuffle<T>(IList<T> items, Random random)
    {
        for (var i = items.Count - 1; i > 0; i--)
        {
            var j = random.Next(i + 1);
            (items[i], items[j]) = (items[j], items[i]);
        }
    }

    private static string Hash(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static string Sha256File(string path)
        => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
}
