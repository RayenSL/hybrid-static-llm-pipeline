using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.Layer3;

/// <summary>
/// Layer 2 on an arbitrary solution. The transfer probe reports the same three layers as the
/// confirmatory experiment, so whole-solution impact is scored per sealed artefact against a single
/// pristine baseline. Two properties matter beyond the arithmetic: a repair that never built is not
/// scored at all, and documentation loss is counted directly because the CA instrument does not see it
/// (missing documentation is a compiler warning, not a CA rule).
/// </summary>
public sealed class ExternalQualityEvaluatorTests : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
    };

    private readonly string _root = Path.Combine(
        Path.GetTempPath(), $"external-quality-tests-{Guid.NewGuid():N}");
    private readonly string _product;
    private readonly string _solution;
    private readonly string _artifacts;

    private const string Pristine =
        "/// <summary>Adds.</summary>\n// a note\nnamespace Demo; public class Thing { public int V() => 7; }\n";

    public ExternalQualityEvaluatorTests()
    {
        _product = Path.Combine(_root, "product");
        _artifacts = Path.Combine(_root, "artifacts");
        Directory.CreateDirectory(Path.Combine(_product, "src"));
        Directory.CreateDirectory(_artifacts);
        _solution = Path.Combine(_product, "Product.sln");
        File.WriteAllText(_solution, "solution");
        File.WriteAllText(Path.Combine(_product, "src", "Target.cs"), Pristine);
    }

    private string WriteArtifact(bool? buildPassed, string finalSource)
    {
        var artifact = new MaterializedSourceArtifact
        {
            ArtifactId = Guid.NewGuid().ToString("N"),
            Timestamp = DateTimeOffset.UnixEpoch,
            Architecture = "ungrounded_single_shot",
            GroundingEnabled = false,
            ControlStructure = "single_shot",
            VisibleTestsEnabled = false,
            VisibleTestAvailable = false,
            RunNumber = 1,
            RelativeFile = "src/Target.cs",
            FinalSource = finalSource,
            SourceSha256 = MaterializedSourceArtifactWriter.Sha256(finalSource),
            BuildPassed = buildPassed
        };
        var path = Path.Combine(_artifacts, $"{artifact.ArtifactId}.json");
        File.WriteAllText(path, JsonSerializer.Serialize(artifact, JsonOptions), new UTF8Encoding(false));
        return path;
    }

    private ExternalQualityEvaluator Evaluator(
        FakeScanner scanner, IReadOnlyList<string>? buildArguments = null,
        IReadOnlyList<string>? skipDirectories = null) =>
        new(scanner, _solution,
            buildArguments ?? ["--no-restore"],
            timeoutSeconds: 30,
            workingCopySkipDirectories: skipDirectories ?? ["bin", ".git", ".vs", ".idea"],
            build: (_, _, _) => Task.FromResult((true, "ok")));

    [Fact]
    public async Task A_resolved_smell_and_an_introduced_diagnostic_are_both_reported()
    {
        var scanner = new FakeScanner(
            before: Scan(smellKeys: ["LongMethod|src/Target.cs|Demo.Thing.V"],
                         headline: new() { ["Performance"] = 4 }, headlineTotal: 4, allTotal: 9),
            after: Scan(smellKeys: [],
                        headline: new() { ["Performance"] = 5 }, headlineTotal: 5, allTotal: 10));
        var evaluator = Evaluator(scanner);
        await evaluator.CaptureBaselineAsync(TextWriter.Null);

        var result = await evaluator.EvaluateOneAsync(WriteArtifact(true, "namespace Demo; public class Thing { }\n"));

        Assert.Equal("scored", result.Outcome);
        Assert.Equal(1, result.SmellTotalBefore);
        Assert.Equal(0, result.SmellTotalAfter);
        Assert.Equal(4, result.CaHeadlineBefore);
        Assert.Equal(5, result.CaHeadlineAfter);
        Assert.Equal(1, result.CaHeadlineCategoryDelta!["Performance"]);
        Assert.Single(result.SmellsResolved!);
        Assert.Empty(result.SmellsIntroduced!);
    }

    [Fact]
    public async Task Only_categories_that_moved_appear_in_the_delta()
    {
        var scanner = new FakeScanner(
            before: Scan([], new() { ["Design"] = 3, ["Naming"] = 2 }, 5, 5),
            after: Scan([], new() { ["Design"] = 3, ["Naming"] = 7 }, 10, 10));
        var evaluator = Evaluator(scanner);
        await evaluator.CaptureBaselineAsync(TextWriter.Null);

        var result = await evaluator.EvaluateOneAsync(WriteArtifact(true, "namespace Demo;\n"));

        Assert.Equal(5, result.CaHeadlineCategoryDelta!["Naming"]);
        Assert.DoesNotContain("Design", result.CaHeadlineCategoryDelta!.Keys);
    }

    [Fact]
    public async Task Documentation_loss_is_counted_because_the_ca_instrument_does_not_see_it()
    {
        var scanner = new FakeScanner(Scan([], [], 0, 0), Scan([], [], 0, 0));
        var evaluator = Evaluator(scanner);
        await evaluator.CaptureBaselineAsync(TextWriter.Null);

        var result = await evaluator.EvaluateOneAsync(
            WriteArtifact(true, "namespace Demo; public class Thing { public int V() => 7; }\n"));

        Assert.Equal(1, result.DocCommentLinesBefore);
        Assert.Equal(0, result.DocCommentLinesAfter);
        Assert.Equal(1, result.CommentLinesBefore);
        Assert.Equal(0, result.CommentLinesAfter);
    }

    [Fact]
    public async Task A_repair_that_never_built_is_not_scored_but_still_reports_documentation()
    {
        var scanner = new FakeScanner(Scan([], [], 0, 0), Scan([], [], 0, 0));
        var evaluator = Evaluator(scanner);
        await evaluator.CaptureBaselineAsync(TextWriter.Null);

        var result = await evaluator.EvaluateOneAsync(WriteArtifact(false, "namespace Demo;\n"));

        Assert.Equal("production_build_failed", result.Outcome);
        Assert.Null(result.CaHeadlineAfter);
        Assert.Equal(1, result.DocCommentLinesBefore);
        Assert.Equal(1, scanner.Scans); // baseline only; no per-artefact analyser build was spent
    }

    [Fact]
    public async Task A_no_restore_analyser_build_with_obj_omitted_is_refused()
    {
        var scanner = new FakeScanner(Scan([], [], 0, 0), Scan([], [], 0, 0));
        var evaluator = Evaluator(scanner, skipDirectories: ["bin", "obj", ".git"]);

        var error = await Assert.ThrowsAsync<InvalidDataException>(
            () => evaluator.CaptureBaselineAsync(TextWriter.Null));

        Assert.Contains("must retain obj", error.Message);
    }

    [Fact]
    public async Task A_tampered_artefact_is_rejected_before_any_analyser_build()
    {
        var scanner = new FakeScanner(Scan([], [], 0, 0), Scan([], [], 0, 0));
        var evaluator = Evaluator(scanner);
        await evaluator.CaptureBaselineAsync(TextWriter.Null);
        var path = WriteArtifact(true, "namespace Demo;\n");
        var text = await File.ReadAllTextAsync(path);
        await File.WriteAllTextAsync(path, text.Replace("namespace Demo;", "namespace Tampered;"));

        await Assert.ThrowsAsync<InvalidDataException>(() => evaluator.EvaluateOneAsync(path));
        Assert.Equal(1, scanner.Scans);
    }

    [Fact]
    public async Task Directory_evaluation_uses_bounded_parallelism_and_preserves_artifact_order()
    {
        WriteArtifact(true, "namespace Demo; // a\n");
        WriteArtifact(true, "namespace Demo; // b\n");
        WriteArtifact(true, "namespace Demo; // c\n");
        var scanner = new ConcurrencyScanner(Scan([], [], 0, 0));
        var evaluator = new ExternalQualityEvaluator(
            scanner, _solution, ["--no-restore"], 30,
            ["bin", ".git", ".vs", ".idea"],
            (_, _, _) => Task.FromResult((true, "ok")));
        await evaluator.CaptureBaselineAsync(TextWriter.Null);
        var progress = new StringWriter();

        var results = await evaluator.EvaluateDirectoryAsync(
            _artifacts, progress, maxDegreeOfParallelism: 2);

        Assert.Equal(2, scanner.MaximumActive);
        Assert.Equal(
            results.Select(result => result.ArtifactRef).Order(StringComparer.Ordinal),
            results.Select(result => result.ArtifactRef));
        Assert.Equal(3, progress.ToString().Split('\n', StringSplitOptions.RemoveEmptyEntries).Length);
    }

    private static SolutionQualityScan Scan(
        IReadOnlyList<string> smellKeys, Dictionary<string, int> headline, int headlineTotal, int allTotal) =>
        new()
        {
            SmellCountsByType = new Dictionary<string, int>(),
            SmellTotal = smellKeys.Count,
            SmellKeys = smellKeys,
            CaHeadlineByRule = new Dictionary<string, int>(),
            CaHeadlineByCategory = headline,
            CaHeadlineTotal = headlineTotal,
            CaAllByRule = new Dictionary<string, int>(),
            CaAllByCategory = new Dictionary<string, int>(),
            CaAllTotal = allTotal,
            CompilerObsoleteCount = 0,
            Diagnostics = [],
            CaAvailable = true
        };

    public void Dispose()
    {
        try { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
        catch { /* best effort */ }
    }

    private sealed class FakeScanner(SolutionQualityScan before, SolutionQualityScan after) : ISolutionQualityScanner
    {
        public int Scans { get; private set; }

        public Task<SolutionQualityScan> ScanAsync(
            string solutionPath, string sarifRoot, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("the evaluator always uses the dedicated analyser build");

        public Task<SolutionQualityScan> BuildAndScanAsync(
            string solutionPath, string workingRoot,
            Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> build,
            int buildTimeoutSeconds, CancellationToken cancellationToken = default)
        {
            Scans++;
            return Task.FromResult(Scans == 1 ? before : after);
        }
    }

    private sealed class ConcurrencyScanner(SolutionQualityScan scan) : ISolutionQualityScanner
    {
        private int _scans;
        private int _active;
        private int _maximumActive;

        public int MaximumActive => _maximumActive;

        public Task<SolutionQualityScan> ScanAsync(
            string solutionPath, string sarifRoot, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public async Task<SolutionQualityScan> BuildAndScanAsync(
            string solutionPath, string workingRoot,
            Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> build,
            int buildTimeoutSeconds, CancellationToken cancellationToken = default)
        {
            if (Interlocked.Increment(ref _scans) == 1) return scan;
            var now = Interlocked.Increment(ref _active);
            int observed;
            do
            {
                observed = _maximumActive;
                if (observed >= now) break;
            } while (Interlocked.CompareExchange(ref _maximumActive, now, observed) != observed);
            await Task.Delay(100, cancellationToken);
            Interlocked.Decrement(ref _active);
            return scan;
        }
    }
}
