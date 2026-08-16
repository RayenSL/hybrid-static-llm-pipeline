using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>One whole-solution quality verdict for a frozen final-source artefact.</summary>
public sealed record ExternalQualityResult
{
    public required string EvaluationId { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required string ArtifactId { get; init; }
    public required string ArtifactRef { get; init; }
    public required string SourceSha256 { get; init; }
    public required string RelativeFile { get; init; }
    public required string Outcome { get; init; }

    public int? SmellTotalBefore { get; init; }
    public int? SmellTotalAfter { get; init; }
    public int? CaHeadlineBefore { get; init; }
    public int? CaHeadlineAfter { get; init; }
    public int? CaAllBefore { get; init; }
    public int? CaAllAfter { get; init; }

    /// <summary>Headline-tier delta per CA category; only categories that moved are recorded.</summary>
    public IReadOnlyDictionary<string, int>? CaHeadlineCategoryDelta { get; init; }
    /// <summary>Headline-tier delta per rule ID; only rules that moved are recorded.</summary>
    public IReadOnlyDictionary<string, int>? CaHeadlineRuleDelta { get; init; }
    /// <summary>Whole-solution detector findings present after but not before — collateral.</summary>
    public IReadOnlyList<string>? SmellsIntroduced { get; init; }
    /// <summary>Whole-solution detector findings present before but not after.</summary>
    public IReadOnlyList<string>? SmellsResolved { get; init; }

    /// <summary>Comment and documentation lines in the repaired file, against the pristine file. The CA
    /// instrument does not cover these: missing documentation is a compiler warning, not a CA rule.</summary>
    public int? DocCommentLinesBefore { get; init; }
    public int? DocCommentLinesAfter { get; init; }
    public int? CommentLinesBefore { get; init; }
    public int? CommentLinesAfter { get; init; }

    public double DurationMs { get; init; }
    public string? Note { get; init; }
}

/// <summary>
/// Measures Layer 2 — whole-solution quality impact — for each sealed final-source artefact of an
/// arbitrary C# solution, so the transfer probe reports the same three layers as the corpus rather
/// than only the target metric and behaviour.
///
/// Each artefact is scored in its own copy of the pristine tree with exactly one file replaced, and
/// compared against a single pristine baseline scan of the same tree. The analyser build is dedicated:
/// its pass/fail is ignored, because whether the repair compiles was already decided by the campaign's
/// own gate. Artefacts whose repair never built are not scored.
/// </summary>
public sealed class ExternalQualityEvaluator(
    ISolutionQualityScanner scanner,
    string solutionPath,
    IReadOnlyList<string> buildArguments,
    int timeoutSeconds,
    IReadOnlyList<string>? workingCopySkipDirectories = null,
    Func<string, int, CancellationToken, Task<(bool Ok, string Output)>>? build = null)
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    private readonly Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> _build =
        build ?? ((solution, timeout, ct) => DotnetBuilder.BuildAsync(solution, timeout, buildArguments, ct));

    private SolutionQualityScan? _baseline;

    /// <summary>
    /// Scans the pristine tree once. Every artefact delta is taken against this, so the analyser build
    /// happens on the same materialisation path the repaired states use.
    /// </summary>
    public async Task<SolutionQualityScan> CaptureBaselineAsync(
        TextWriter log, CancellationToken cancellationToken = default)
    {
        WorkingCopy.GuardRestoreArguments(buildArguments, workingCopySkipDirectories, "the analyser build");
        var productRoot = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-quality-baseline-{Guid.NewGuid():N}");
        try
        {
            WorkingCopy.Create(productRoot, workingRoot, workingCopySkipDirectories);
            var workingSolution = Path.Combine(workingRoot, Path.GetFileName(solutionPath));
            log.WriteLine($"baseline analyser scan: {workingRoot}");
            _baseline = await scanner.BuildAndScanAsync(
                workingSolution, workingRoot, _build, timeoutSeconds, cancellationToken);
            log.WriteLine($"baseline  smells {_baseline.SmellTotal}"
                + $"  CA headline {_baseline.CaHeadlineTotal}  CA all {_baseline.CaAllTotal}"
                + (_baseline.CaAvailable ? "" : "  (CA UNAVAILABLE)"));
            return _baseline;
        }
        finally
        {
            WorkingCopy.TryDelete(workingRoot);
        }
    }

    public async Task<IReadOnlyList<ExternalQualityResult>> EvaluateDirectoryAsync(
        string artifactDirectory, TextWriter log, int maxDegreeOfParallelism = 1,
        CancellationToken cancellationToken = default)
    {
        if (_baseline is null) await CaptureBaselineAsync(log, cancellationToken);

        var paths = Directory.EnumerateFiles(artifactDirectory, "*.json", SearchOption.TopDirectoryOnly)
            .OrderBy(p => p, StringComparer.Ordinal)
            .ToList();
        var results = new ExternalQualityResult?[paths.Count];
        using var gate = new SemaphoreSlim(Math.Max(1, maxDegreeOfParallelism));
        var tasks = paths.Select(async (path, index) =>
        {
            await gate.WaitAsync(cancellationToken);
            try
            {
                var result = await EvaluateOneAsync(path, cancellationToken);
                results[index] = result;
                lock (log)
                    log.WriteLine($"[{index + 1}/{paths.Count}] {result.Outcome,-24} "
                        + (result.CaHeadlineAfter is null
                            ? Path.GetFileName(path)
                            : $"CA headline {result.CaHeadlineBefore}->{result.CaHeadlineAfter}"
                              + $"  smells {result.SmellTotalBefore}->{result.SmellTotalAfter}"));
            }
            finally
            {
                gate.Release();
            }
        });
        await Task.WhenAll(tasks);
        return results.Select(result => result!).ToList();
    }

    public async Task<ExternalQualityResult> EvaluateOneAsync(
        string artifactPath, CancellationToken cancellationToken = default)
    {
        var artifact = JsonSerializer.Deserialize<MaterializedSourceArtifact>(
                           await File.ReadAllTextAsync(artifactPath, cancellationToken), JsonOptions)
                       ?? throw new InvalidDataException("materialized-source artefact is empty or invalid");
        if (!string.Equals(MaterializedSourceArtifactWriter.Sha256(artifact.FinalSource),
                           artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized-source artefact hash does not match final source");

        var baseline = _baseline ?? throw new InvalidOperationException("baseline scan has not been captured");
        var productRoot = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var relative = artifact.RelativeFile.Replace('/', Path.DirectorySeparatorChar);
        var pristineFile = Path.GetFullPath(Path.Combine(productRoot, relative));
        if (!pristineFile.StartsWith(productRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized source path is outside the product root");

        var (docBefore, commentBefore) = CountCommentary(await File.ReadAllTextAsync(pristineFile, cancellationToken));
        var (docAfter, commentAfter) = CountCommentary(artifact.FinalSource);

        if (artifact.BuildPassed != true)
            return new ExternalQualityResult
            {
                EvaluationId = Guid.NewGuid().ToString("N"),
                Timestamp = DateTimeOffset.UtcNow,
                ArtifactId = artifact.ArtifactId,
                ArtifactRef = Path.GetFullPath(artifactPath),
                SourceSha256 = artifact.SourceSha256,
                RelativeFile = artifact.RelativeFile,
                Outcome = artifact.BuildPassed == false ? "production_build_failed" : "production_build_not_recorded",
                DocCommentLinesBefore = docBefore,
                DocCommentLinesAfter = docAfter,
                CommentLinesBefore = commentBefore,
                CommentLinesAfter = commentAfter,
                Note = "repair never built; whole-solution quality not scored"
            };

        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-quality-{Guid.NewGuid():N}");
        var stopwatch = Stopwatch.StartNew();
        try
        {
            WorkingCopy.Create(productRoot, workingRoot, workingCopySkipDirectories);
            var workingTarget = Path.Combine(workingRoot, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
            await File.WriteAllTextAsync(workingTarget, artifact.FinalSource, new UTF8Encoding(false), cancellationToken);

            var workingSolution = Path.Combine(workingRoot, Path.GetFileName(solutionPath));
            var after = await scanner.BuildAndScanAsync(
                workingSolution, workingRoot, _build, timeoutSeconds, cancellationToken);
            stopwatch.Stop();

            var beforeSmells = baseline.SmellKeys.ToHashSet(StringComparer.Ordinal);
            var afterSmells = after.SmellKeys.ToHashSet(StringComparer.Ordinal);

            return new ExternalQualityResult
            {
                EvaluationId = Guid.NewGuid().ToString("N"),
                Timestamp = DateTimeOffset.UtcNow,
                ArtifactId = artifact.ArtifactId,
                ArtifactRef = Path.GetFullPath(artifactPath),
                SourceSha256 = artifact.SourceSha256,
                RelativeFile = artifact.RelativeFile,
                Outcome = after.CaAvailable ? "scored" : "scored_without_ca",
                SmellTotalBefore = baseline.SmellTotal,
                SmellTotalAfter = after.SmellTotal,
                CaHeadlineBefore = baseline.CaHeadlineTotal,
                CaHeadlineAfter = after.CaHeadlineTotal,
                CaAllBefore = baseline.CaAllTotal,
                CaAllAfter = after.CaAllTotal,
                CaHeadlineCategoryDelta = Delta(baseline.CaHeadlineByCategory, after.CaHeadlineByCategory),
                CaHeadlineRuleDelta = Delta(baseline.CaHeadlineByRule, after.CaHeadlineByRule),
                SmellsIntroduced = afterSmells.Except(beforeSmells, StringComparer.Ordinal)
                    .OrderBy(k => k, StringComparer.Ordinal).ToList(),
                SmellsResolved = beforeSmells.Except(afterSmells, StringComparer.Ordinal)
                    .OrderBy(k => k, StringComparer.Ordinal).ToList(),
                DocCommentLinesBefore = docBefore,
                DocCommentLinesAfter = docAfter,
                CommentLinesBefore = commentBefore,
                CommentLinesAfter = commentAfter,
                DurationMs = stopwatch.Elapsed.TotalMilliseconds,
                Note = after.Note
            };
        }
        finally
        {
            stopwatch.Stop();
            WorkingCopy.TryDelete(workingRoot);
        }
    }

    /// <summary>Only keys whose count moved, so a delta record stays readable.</summary>
    private static IReadOnlyDictionary<string, int> Delta(
        IReadOnlyDictionary<string, int> before, IReadOnlyDictionary<string, int> after)
    {
        var delta = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var key in before.Keys.Concat(after.Keys).Distinct(StringComparer.Ordinal))
        {
            before.TryGetValue(key, out var b);
            after.TryGetValue(key, out var a);
            if (a != b) delta[key] = a - b;
        }
        return delta;
    }

    /// <summary>
    /// Documentation and ordinary comment lines. Deleting either preserves behaviour and moves no
    /// triggering metric, and the CA instrument does not report it, so it is counted directly.
    /// </summary>
    private static (int DocLines, int CommentLines) CountCommentary(string source)
    {
        var doc = 0;
        var comment = 0;
        foreach (var line in source.Split('\n'))
        {
            var trimmed = line.TrimStart();
            if (trimmed.StartsWith("///", StringComparison.Ordinal)) doc++;
            else if (trimmed.StartsWith("//", StringComparison.Ordinal)) comment++;
        }
        return (doc, comment);
    }
}
