using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Evaluates common final-source artefacts against the frozen private oracle. This class has no LLM,
/// detector, retry, or repair dependency and ignores all experimental-factor fields in the artefact.
/// </summary>
public sealed class PrivateLayer3Evaluator(
    string solutionPath,
    string oracleRoot,
    string oracleManifestVersion,
    int timeoutSeconds,
    Func<string, string, int, CancellationToken, Task<(bool Ok, string Output)>>? executeOracle = null)
{
    private static readonly string[] SkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };
    private readonly Func<string, string, int, CancellationToken, Task<(bool Ok, string Output)>> _executeOracle
        = executeOracle ?? RunOracleAsync;

    public async Task<IReadOnlyList<PrivateLayer3Result>> EvaluateDirectoryAsync(
        string artifactDirectory,
        TextWriter progress,
        int maxDegreeOfParallelism = 1,
        CancellationToken cancellationToken = default)
    {
        var paths = Directory.EnumerateFiles(artifactDirectory, "*.json", SearchOption.TopDirectoryOnly)
            .Order(StringComparer.Ordinal)
            .ToList();
        var results = new PrivateLayer3Result?[paths.Count];
        using var gate = new SemaphoreSlim(Math.Max(1, maxDegreeOfParallelism));
        var tasks = paths.Select(async (path, index) =>
        {
            await gate.WaitAsync(cancellationToken);
            try
            {
                var result = await EvaluateOneAsync(path, cancellationToken);
                results[index] = result;
                lock (progress)
                    progress.WriteLine(
                        $"[{index + 1}/{paths.Count}] {result.ArtifactId}: " +
                        (result.Evaluated ? result.Passed == true ? "PASS" : "REGRESSION" : $"NOT-RUN ({result.NotRunReason})"));
            }
            finally
            {
                gate.Release();
            }
        });
        await Task.WhenAll(tasks);
        return results.Select(result => result!).ToList();
    }

    public async Task<PrivateLayer3Result> EvaluateOneAsync(
        string artifactPath,
        CancellationToken cancellationToken = default)
    {
        var artifactJson = await File.ReadAllTextAsync(artifactPath, cancellationToken);
        var artifact = JsonSerializer.Deserialize<MaterializedSourceArtifact>(artifactJson, JsonOptions)
            ?? throw new InvalidDataException("materialized-source artefact is empty or invalid");
        var actualHash = MaterializedSourceArtifactWriter.Sha256(artifact.FinalSource);
        if (!string.Equals(actualHash, artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized-source artefact hash does not match final source");

        if (artifact.BuildPassed != true)
            return Result(artifact, artifactPath, false, null, null, null, 0,
                artifact.BuildPassed == false ? "production_build_failed" : "production_build_not_recorded", null);

        var corpusRoot = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var relative = artifact.RelativeFile.Replace('/', Path.DirectorySeparatorChar);
        var target = Path.GetFullPath(Path.Combine(corpusRoot, relative));
        if (!target.StartsWith(corpusRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("materialized source path is outside the corpus root");

        var characterization = Path.Combine(Path.GetFullPath(oracleRoot), "characterization");
        var golden = Path.Combine(Path.GetFullPath(oracleRoot), "golden");
        if (!Directory.Exists(characterization) || !Directory.Exists(golden))
            throw new DirectoryNotFoundException("private oracle must contain characterization and golden directories");

        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-private-layer3-{Guid.NewGuid():N}");
        var stopwatch = Stopwatch.StartNew();
        try
        {
            CopyTree(corpusRoot, workingRoot);
            var workingTarget = Path.Combine(workingRoot, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
            await File.WriteAllTextAsync(workingTarget, artifact.FinalSource, new UTF8Encoding(false), cancellationToken);

            // The frozen harness references sibling projects such as ..\Ordering\Ordering.csproj.
            // Corpus projects live under <solution-root>/src, so place the copied harness there too.
            var workingCharacterization = Path.Combine(workingRoot, "src", "characterization");
            CopyTree(characterization, workingCharacterization);
            var project = Path.Combine(workingCharacterization, "Characterization.csproj");
            var execution = await _executeOracle(project, golden, timeoutSeconds, cancellationToken);
            stopwatch.Stop();
            var passing = CountLines(execution.Output, "PASS  ");
            var failing = CountLines(execution.Output, "REGRESSION  ") + CountLines(execution.Output, "MISSING-GOLDEN  ");
            return Result(
                artifact, artifactPath, true, execution.Ok, passing, failing,
                stopwatch.Elapsed.TotalMilliseconds, null, Tail(execution.Output, 6000));
        }
        finally
        {
            stopwatch.Stop();
            TryDeleteTree(workingRoot);
        }
    }

    private PrivateLayer3Result Result(
        MaterializedSourceArtifact artifact,
        string artifactPath,
        bool evaluated,
        bool? passed,
        int? passing,
        int? failing,
        double durationMs,
        string? notRunReason,
        string? outputTail) => new()
    {
        EvaluationId = Guid.NewGuid().ToString("N"),
        Timestamp = DateTimeOffset.UtcNow,
        ArtifactId = artifact.ArtifactId,
        ArtifactRef = Path.GetFullPath(artifactPath),
        SourceSha256 = artifact.SourceSha256,
        OracleManifestVersion = oracleManifestVersion,
        Evaluated = evaluated,
        Passed = passed,
        PassingDrivers = passing,
        FailingDrivers = failing,
        DurationMs = durationMs,
        NotRunReason = notRunReason,
        OutputTail = outputTail
    };

    private static async Task<(bool Ok, string Output)> RunOracleAsync(
        string project,
        string golden,
        int timeout,
        CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "dotnet",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        foreach (var argument in new[] { "run", "--project", project, "--", "--check", golden })
            psi.ArgumentList.Add(argument);
        using var process = new Process { StartInfo = psi };
        var output = new StringBuilder();
        process.OutputDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data is not null) output.AppendLine(e.Data); };
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(TimeSpan.FromSeconds(Math.Max(1, timeout)));
        try
        {
            await process.WaitForExitAsync(timeoutSource.Token);
        }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            if (cancellationToken.IsCancellationRequested) throw;
            return (false, $"private Layer-3 execution timed out after {timeout}s\n{output}");
        }
        return (process.ExitCode == 0, output.ToString());
    }

    private static int CountLines(string output, string prefix) =>
        output.Replace("\r", string.Empty).Split('\n').Count(line => line.StartsWith(prefix, StringComparison.Ordinal));

    private static void CopyTree(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var relative = Path.GetRelativePath(source, file);
            if (relative.Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries)
                .Any(part => SkipDirs.Contains(part, StringComparer.OrdinalIgnoreCase))) continue;
            var target = Path.Combine(destination, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private static string Tail(string value, int maxChars) => value.Length <= maxChars ? value : value[^maxChars..];

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { }
    }
}
