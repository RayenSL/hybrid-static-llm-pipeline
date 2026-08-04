using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>One post-seal behavioural verdict for a frozen final-source artefact.</summary>
public sealed record ExternalOracleResult
{
    public required string EvaluationId { get; init; }
    public required DateTimeOffset Timestamp { get; init; }
    public required string ArtifactId { get; init; }
    public required string ArtifactRef { get; init; }
    public required string SourceSha256 { get; init; }
    public required string RelativeFile { get; init; }
    public required string Outcome { get; init; }
    public bool? Passed { get; init; }
    public int? PassingDrivers { get; init; }
    public int? FailingDrivers { get; init; }
    public double DurationMs { get; init; }
    public string? OutputTail { get; init; }
}

/// <summary>
/// Runs an external golden-master harness against each sealed final-source artefact, after every
/// repair condition has terminated. Generic over the solution and the harness: the harness is any
/// project that exits zero when the recorded behaviour is unchanged, so the same instrument serves
/// a constructed corpus and an arbitrary industrial solution.
///
/// Each artefact is evaluated in its own copy of the pristine tree with exactly one file replaced,
/// so no artefact can observe another. The harness is built with MSBuild properties pointing at
/// that copy, which is what makes it measure the repaired tree rather than the pristine one.
///
/// Outcomes are deliberately three-valued rather than pass/fail:
///   behaviour_preserved   the harness compiled and every driver matched its golden
///   behavioural_change    the harness compiled and at least one driver differed
///   public_contract_change the harness no longer compiles against the repaired tree
///   production_build_failed / not_recorded  the repair itself never built
/// The third is the case thesis 4.5.5 describes: Extract Class may redistribute members across new
/// types while preserving behaviour, leaving the frozen oracle unable to bind. Scoring that as a
/// behavioural regression would be wrong, so it is recorded separately and left for adjudication.
/// </summary>
public sealed class ExternalOracleEvaluator(
    string solutionPath,
    string harnessProject,
    string goldenDirectory,
    IReadOnlyList<string> harnessProperties,
    IReadOnlyList<string> buildArguments,
    int timeoutSeconds,
    Func<string, IReadOnlyList<string>, int, CancellationToken, Task<(bool Ok, string Output)>>? buildHarness = null,
    Func<string, string, int, CancellationToken, Task<(bool Ok, string Output)>>? runHarness = null)
{
    /// <summary>Substituted with the isolated working-copy root in every harness property.</summary>
    public const string WorkingRootToken = "{WORKING_ROOT}";

    private static readonly string[] SkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    private readonly Func<string, IReadOnlyList<string>, int, CancellationToken, Task<(bool Ok, string Output)>> _buildHarness
        = buildHarness ?? BuildHarnessAsync;
    private readonly Func<string, string, int, CancellationToken, Task<(bool Ok, string Output)>> _runHarness
        = runHarness ?? RunHarnessAsync;

    public async Task<IReadOnlyList<ExternalOracleResult>> EvaluateDirectoryAsync(
        string artifactDirectory, TextWriter log, CancellationToken cancellationToken = default)
    {
        var paths = Directory.EnumerateFiles(artifactDirectory, "*.json", SearchOption.TopDirectoryOnly)
            .OrderBy(p => p, StringComparer.Ordinal)
            .ToList();
        var results = new List<ExternalOracleResult>(paths.Count);
        foreach (var path in paths)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var result = await EvaluateOneAsync(path, cancellationToken);
            results.Add(result);
            log.WriteLine($"{result.Outcome,-24} {Path.GetFileName(path)}");
        }
        return results;
    }

    public async Task<ExternalOracleResult> EvaluateOneAsync(
        string artifactPath, CancellationToken cancellationToken = default)
    {
        var artifact = JsonSerializer.Deserialize<MaterializedSourceArtifact>(
                           await File.ReadAllTextAsync(artifactPath, cancellationToken), JsonOptions)
                       ?? throw new InvalidDataException("materialized-source artefact is empty or invalid");
        if (!string.Equals(MaterializedSourceArtifactWriter.Sha256(artifact.FinalSource),
                           artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized-source artefact hash does not match final source");

        if (artifact.BuildPassed != true)
            return Result(artifact, artifactPath,
                artifact.BuildPassed == false ? "production_build_failed" : "production_build_not_recorded",
                passed: null, passing: null, failing: null, 0, outputTail: null);

        var productRoot = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var relative = artifact.RelativeFile.Replace('/', Path.DirectorySeparatorChar);
        var target = Path.GetFullPath(Path.Combine(productRoot, relative));
        if (!target.StartsWith(productRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized source path is outside the product root");
        if (!Directory.Exists(goldenDirectory))
            throw new DirectoryNotFoundException($"golden directory not found: {goldenDirectory}");
        if (!File.Exists(harnessProject))
            throw new FileNotFoundException("harness project not found", harnessProject);

        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-external-oracle-{Guid.NewGuid():N}");
        var stopwatch = Stopwatch.StartNew();
        try
        {
            CopyTree(productRoot, workingRoot);
            var workingTarget = Path.Combine(workingRoot, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
            await File.WriteAllTextAsync(workingTarget, artifact.FinalSource, new UTF8Encoding(false), cancellationToken);

            var properties = harnessProperties
                .Select(p => p.Replace(WorkingRootToken, workingRoot, StringComparison.Ordinal))
                .Concat(buildArguments)
                .ToList();

            var built = await _buildHarness(harnessProject, properties, timeoutSeconds, cancellationToken);
            if (!built.Ok)
            {
                stopwatch.Stop();
                // Not a regression: the repair may preserve behaviour while moving members so the
                // frozen harness can no longer bind. Thesis 4.5.5 calls this a public-contract change.
                return Result(artifact, artifactPath, "public_contract_change",
                    passed: null, passing: null, failing: null,
                    stopwatch.Elapsed.TotalMilliseconds, Tail(built.Output, 6000));
            }

            var run = await _runHarness(harnessProject, goldenDirectory, timeoutSeconds, cancellationToken);
            stopwatch.Stop();
            var passing = CountLines(run.Output, "PASS  ");
            var failing = CountLines(run.Output, "REGRESSION  ") + CountLines(run.Output, "MISSING-GOLDEN  ");
            return Result(artifact, artifactPath,
                run.Ok ? "behaviour_preserved" : "behavioural_change",
                run.Ok, passing, failing, stopwatch.Elapsed.TotalMilliseconds, Tail(run.Output, 6000));
        }
        finally
        {
            stopwatch.Stop();
            TryDeleteTree(workingRoot);
        }
    }

    private ExternalOracleResult Result(
        MaterializedSourceArtifact artifact, string artifactPath, string outcome,
        bool? passed, int? passing, int? failing, double durationMs, string? outputTail) => new()
    {
        EvaluationId = Guid.NewGuid().ToString("N"),
        Timestamp = DateTimeOffset.UtcNow,
        ArtifactId = artifact.ArtifactId,
        ArtifactRef = Path.GetFullPath(artifactPath),
        SourceSha256 = artifact.SourceSha256,
        RelativeFile = artifact.RelativeFile,
        Outcome = outcome,
        Passed = passed,
        PassingDrivers = passing,
        FailingDrivers = failing,
        DurationMs = durationMs,
        OutputTail = outputTail
    };

    private static Task<(bool Ok, string Output)> BuildHarnessAsync(
        string project, IReadOnlyList<string> arguments, int timeout, CancellationToken cancellationToken)
    {
        var args = new List<string> { "build", project, "--nologo", "-v", "quiet" };
        args.AddRange(arguments);
        return RunAsync(args, timeout, cancellationToken);
    }

    private static Task<(bool Ok, string Output)> RunHarnessAsync(
        string project, string golden, int timeout, CancellationToken cancellationToken)
        => RunAsync(["run", "--project", project, "--no-build", "-v", "quiet", "--", "--check", golden],
                    timeout, cancellationToken);

    private static async Task<(bool Ok, string Output)> RunAsync(
        IReadOnlyList<string> arguments, int timeout, CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "dotnet",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        foreach (var argument in arguments) psi.ArgumentList.Add(argument);

        using var process = new Process { StartInfo = psi };
        var output = new StringBuilder();
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(TimeSpan.FromSeconds(timeout));
        try
        {
            await process.WaitForExitAsync(cts.Token);
        }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { /* best effort */ }
            if (cancellationToken.IsCancellationRequested) throw;
            return (false, $"timed out after {timeout}s\n{output}");
        }
        return (process.ExitCode == 0, output.ToString());
    }

    private static int CountLines(string output, string prefix) =>
        output.Split('\n').Count(line => line.TrimStart().StartsWith(prefix, StringComparison.Ordinal));

    private static void CopyTree(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var relative = Path.GetRelativePath(source, file);
            if (relative.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                .Any(segment => SkipDirs.Contains(segment, StringComparer.OrdinalIgnoreCase)))
                continue;
            var target = Path.Combine(destination, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static string Tail(string value, int maxChars) =>
        value.Length <= maxChars ? value : value[^maxChars..];

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { /* best effort */ }
    }
}
