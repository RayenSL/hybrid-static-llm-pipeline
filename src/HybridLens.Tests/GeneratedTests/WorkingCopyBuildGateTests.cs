using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.Tests.GeneratedTests;

/// <summary>
/// The build gate runs inside an isolated copy of the solution, and what that copy omits decides
/// whether the gate measures the repair at all. A solution that must be built with
/// <c>--no-restore</c> keeps no <c>project.assets.json</c> if <c>obj</c> is left behind, so MSBuild
/// stops with NETSDK1004 before the repaired file is ever compiled and every assignment records a
/// build failure that has nothing to do with the model. Hence the skip list is declarable, and a
/// rejected build now carries the compiler output that tells the two cases apart.
/// </summary>
public sealed class WorkingCopyBuildGateTests : IDisposable
{
    private readonly List<string> _temp = [];

    private const string EditedFile = """
        {"edited_file":"namespace Demo; public class Thing { public int Value() => 7; }","findings":[]}
        """;

    [Fact]
    public async Task By_default_the_working_copy_omits_obj()
    {
        var (solution, instance, artifacts) = MakeCorpus();
        // Observed inside the gate: the working copy is deleted the moment the assignment ends.
        bool? objReached = null;
        var runner = new FactorialSingleShotRunner(
            new StubAdapter(EditedFile), "gpt-5.6-sol", new AlwaysResolvedMeasurer(), solution, 30,
            build: (workingSolution, _, _) =>
            {
                objReached = File.Exists(ObjMarker(workingSolution));
                return Task.FromResult((true, "ok"));
            });

        await runner.RunAttemptAsync(instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: false, visibleTest: null, artifacts, CancellationToken.None);

        Assert.False(objReached, "obj must not reach the working copy by default");
    }

    [Fact]
    public async Task A_declared_skip_list_can_retain_obj_so_a_no_restore_build_can_resolve_its_assets()
    {
        var (solution, instance, artifacts) = MakeCorpus();
        bool? objReached = null;
        var runner = new FactorialSingleShotRunner(
            new StubAdapter(EditedFile), "gpt-5.6-sol", new AlwaysResolvedMeasurer(), solution, 30,
            build: (workingSolution, _, _) =>
            {
                objReached = File.Exists(ObjMarker(workingSolution));
                return Task.FromResult((true, "ok"));
            },
            workingCopySkipDirectories: ["bin", ".git", ".vs", ".idea"]);

        await runner.RunAttemptAsync(instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: false, visibleTest: null, artifacts, CancellationToken.None);

        Assert.True(objReached, "obj/project.assets.json must reach the working copy");
    }

    [Fact]
    public async Task A_rejected_build_records_the_compiler_output()
    {
        var (solution, instance, artifacts) = MakeCorpus();
        var runner = new FactorialSingleShotRunner(
            new StubAdapter(EditedFile), "gpt-5.6-sol", new AlwaysResolvedMeasurer(), solution, 30,
            build: (_, _, _) => Task.FromResult((false, "error NETSDK1004: Assets file not found")));

        var record = await runner.RunAttemptAsync(instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: false, visibleTest: null, artifacts, CancellationToken.None);

        Assert.False(record.BuildPassed);
        Assert.Equal(VerifiedRepairOutcome.BuildFails, record.VerifiedRepairLadder);
        Assert.Contains("NETSDK1004", record.BuildOutputTail);
    }

    [Fact]
    public async Task A_passing_build_records_no_compiler_output()
    {
        var (solution, instance, artifacts) = MakeCorpus();
        var runner = new FactorialSingleShotRunner(
            new StubAdapter(EditedFile), "gpt-5.6-sol", new AlwaysResolvedMeasurer(), solution, 30,
            build: (_, _, _) => Task.FromResult((true, "Build succeeded")));

        var record = await runner.RunAttemptAsync(instance, 1, grounded: false, groundingBlock: null,
            visibleTestsEnabled: false, visibleTest: null, artifacts, CancellationToken.None);

        Assert.True(record.BuildPassed);
        Assert.Null(record.BuildOutputTail);
    }

    private static string ObjMarker(string workingSolution) =>
        Path.Combine(Path.GetDirectoryName(workingSolution)!, "Demo", "obj", "project.assets.json");

    private (string Solution, KnownInstance Instance, string Artifacts) MakeCorpus()
    {
        var root = Path.Combine(Path.GetTempPath(), $"hl-working-copy-{Guid.NewGuid():N}");
        var projectDir = Path.Combine(root, "Demo");
        Directory.CreateDirectory(Path.Combine(projectDir, "obj"));
        _temp.Add(root);

        var solution = Path.Combine(root, "Corpus.sln");
        File.WriteAllText(solution, "Microsoft Visual Studio Solution File");
        File.WriteAllText(Path.Combine(projectDir, "Demo.csproj"),
            "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>");
        File.WriteAllText(Path.Combine(projectDir, "obj", "project.assets.json"), "{}");
        var file = Path.Combine(projectDir, "Thing.cs");
        File.WriteAllText(file, "namespace Demo; public class Thing { public int Value() => 7; }");

        var instance = KnownInstance.Create(
            AntiPatternType.GodClass, file, "Demo.Thing", 1, Severity.Critical, "public class Thing");
        return (solution, instance, Path.Combine(root, "artifacts"));
    }

    public void Dispose()
    {
        foreach (var path in _temp)
        {
            try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
            catch { /* best effort */ }
        }
    }

    private sealed class StubAdapter(string content) : ILlmAdapter
    {
        public Task<LlmResponse> CompleteAsync(LlmRequest request, CancellationToken cancellationToken = default)
            => Task.FromResult(new LlmResponse { Content = content, InputTokens = 10, OutputTokens = 10 });
        public Task<LlmResponse> CompleteAsync(LlmConversation conversation, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }

    private sealed class AlwaysResolvedMeasurer : IRepairMeasurer
    {
        public Task<RemeasureResult> RemeasureAsync(
            AntiPatternType type, string workingFilePath, string instanceSymbol, CancellationToken cancellationToken = default)
            => Task.FromResult(new RemeasureResult(false, null));
    }
}
