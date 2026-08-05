using System.Diagnostics;
using System.Text;
using System.Text.Json;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;

namespace HybridLens.Pipeline;

/// <summary>
/// Runs an iterative, compiler-in-the-loop architecture arm (§4.4.1, Appendix E prompt v2.0.2). The
/// agent works in an AUTONOMOUS LOOP over a whole source FILE: each turn it either edits the file and
/// requests a build, or declares completion. Its only tool is the compiler — after every edit the
/// pipeline builds a working copy of the corpus and feeds the result (success or diagnostics) back as
/// the next user turn. The loop ends when the agent declares completion or the frozen iteration budget
/// is exhausted (a distinct outcome, §4.8.1).
///
/// The same runner serves BOTH iterative arms of the §4.4.1 2×2; <paramref name="architecture"/>
/// selects which:
///   • <c>"agentic"</c> (ungrounded) — the agent receives neutral target coordinates but no static diagnosis; it diagnoses,
///     explains, and repairs for itself, so the arm stays ungrounded and is scored for recall/precision.
///   • <c>"grounded_iterative"</c> — the opening user prompt is seeded with the analyser's Structural
///     finding block (passed via <c>groundingByFile</c>), routing the detector's output into the same
///     loop. This relieves the arm of detection, so it emits no detection rows; the H1c contrast
///     (grounded-iterative vs ungrounded agentic) then varies grounding alone (§5.1.5).
///
/// Row types written per (file × run):
///   • detection finding rows (ungrounded arm only) — one per reported finding, matched to the known
///     instances by type + line-in-range OR simple-symbol overlap (§4.5.1), feeding recall and precision; and
///   • verified-repair rows — TWO per known instance, scoring the agent's edited solution directly
///     (build gate → detector re-run; no separate applier, §4.7.1): a <c>"final"</c> snapshot and a
///     <c>"first_build"</c> snapshot (the state submitted at the first build, before any compiler
///     feedback — the single-pass cell of the 2×2, recovered by re-scoring that frozen state, §4.4.1).
///
/// The frozen corpus is never mutated: the tree is copied once to a temp working directory and the
/// edited file is restored to pristine between runs. The full trajectory is frozen as an artefact
/// (reproducibility at the artefact level, §4.8.5). Runs sequentially.
/// </summary>
public sealed class AgenticRunner(
    ILlmAdapter adapter,
    string modelName,
    IRepairMeasurer measurer,
    string solutionPath,
    int iterationBudget,
    int buildTimeoutSeconds,
    Func<string, int, CancellationToken, Task<(bool Ok, string Output)>>? build = null,
    string architecture = "agentic",
    ISolutionQualityScanner? qualityScanner = null,
    Func<GeneratedTestSource, string, int, CancellationToken, Task<GeneratedTestExecutionResult>>? executeVisibleTest = null,
    IReadOnlyList<string>? workingCopySkipDirectories = null)
{
    /// <summary>Directories left out of the working copy. See
    /// <see cref="HybridLens.Core.Models.FactorialCampaignManifest.WorkingCopySkipDirectories"/>:
    /// a solution built with <c>--no-restore</c> must retain <c>obj</c>.</summary>
    private readonly string[] _skipDirs = workingCopySkipDirectories is { Count: > 0 } declared
        ? [.. declared] : FactorialSingleShotRunner.DefaultSkipDirs;

    /// <summary>The compiler tool. Defaults to a real <c>dotnet build</c>; overridable for tests.</summary>
    private readonly Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> _build
        = build ?? DotnetBuilder.BuildAsync;

    private readonly Func<GeneratedTestSource, string, int, CancellationToken, Task<GeneratedTestExecutionResult>> _executeVisibleTest
        = executeVisibleTest ?? GeneratedTestAdmissionRunner.ExecuteOnceAsync;

    /// <summary>Architecture tag stamped on every row: "agentic" (ungrounded) or "grounded_iterative".</summary>
    private readonly string _architecture = ValidateArchitecture(architecture);

    /// <summary>Only the target-only arm must diagnose and report the target; the grounded arm is supplied the findings, so it
    /// emits no detection rows and treats every seeded instance as recovered by construction (§4.4.1).</summary>
    private readonly bool _performsDetection = ValidateArchitecture(architecture) == "agentic";

    /// <summary>Shared pristine-corpus quality baseline (the "before" for every trajectory), captured once when <c>--quality-diff</c> is on.</summary>
    private SolutionQualityScan? _qualityBaseline;

    /// <param name="knownInstances">Ground-truth instances (the rated set), grouped internally by file.</param>
    /// <param name="runs">Trajectories per file (default 3).</param>
    /// <param name="maxInputTokenGuard">Heuristic token cap; over this the file is flagged as likely truncated.</param>
    /// <param name="trajectoryDir">Directory for the frozen per-trajectory artefacts.</param>
    /// <param name="sweepFiles">
    /// Optional full set of source files to process. When given (the whole corpus), files without a
    /// seeded instance contribute precision evidence — any detection on them is a scoreable spurious
    /// finding (§4.5.1). When null, only the files holding a seeded instance are processed.
    /// </param>
    /// <param name="groundingByFile">
    /// Grounded-iterative arm only: full-path → the analyser's Structural finding block to seed the
    /// opening user prompt for that file (§5.1.5). Null/absent ⇒ the ungrounded agentic prompt (whole
    /// file, no annotation). Keyed case-insensitively to match the resolved file paths.
    /// </param>
    public async Task RunAsync(
        IReadOnlyList<KnownInstance> knownInstances,
        int runs,
        IRunStore runStore,
        int maxInputTokenGuard,
        string trajectoryDir,
        TextWriter progress,
        CancellationToken ct,
        IReadOnlyList<string>? sweepFiles = null,
        IReadOnlyDictionary<string, string>? groundingByFile = null,
        IReadOnlyDictionary<string, LoadedGeneratedTest>? visibleTestsByFile = null,
        bool visibleTestsEnabled = false,
        string? finalArtifactDirectory = null,
        int runNumberOffset = 0)
    {
        if (runNumberOffset < 0) throw new ArgumentOutOfRangeException(nameof(runNumberOffset));
        if (!visibleTestsEnabled && visibleTestsByFile is { Count: > 0 })
            throw new ArgumentException("visible tests cannot be supplied to a test-disabled cell", nameof(visibleTestsByFile));
        if (_performsDetection && groundingByFile is { Count: > 0 })
            throw new ArgumentException("the ungrounded iterative architecture cannot receive finding blocks", nameof(groundingByFile));

        var knownByFile = knownInstances
            .GroupBy(k => Path.GetFullPath(k.FilePath), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g.ToList(), StringComparer.OrdinalIgnoreCase);
        if (!_performsDetection)
        {
            if (groundingByFile is null)
                throw new ArgumentException("the grounded iterative architecture requires finding blocks", nameof(groundingByFile));
            var missingGrounding = knownByFile.Keys.FirstOrDefault(
                file => !groundingByFile.TryGetValue(file, out var block) || string.IsNullOrWhiteSpace(block));
            if (missingGrounding is not null)
                throw new ArgumentException(
                    $"the grounded iterative architecture has no finding block for: {missingGrounding}",
                    nameof(groundingByFile));
        }

        var files = (sweepFiles is { Count: > 0 }
                ? sweepFiles.Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase)
                : knownByFile.Keys)
            .ToList();

        var corpusRoot  = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-agentic-{Guid.NewGuid():N}");
        var workingSln  = Path.Combine(workingRoot, Path.GetFileName(solutionPath));

        var withInstances = files.Count(knownByFile.ContainsKey);
        progress.WriteLine(
            $"{_architecture}: {files.Count} file(s) ({withInstances} with seeded instances), " +
            $"{knownInstances.Count} known instance(s), model={modelName}, runs={runs}, " +
            $"budget={iterationBudget}, prompt={PromptTemplate.AgenticVersion}/{PromptTemplate.AgenticVisibleTestVersion}");
        progress.WriteLine($"  working copy: {workingRoot}");
        Directory.CreateDirectory(trajectoryDir);
        var materializedDirectory = finalArtifactDirectory ?? trajectoryDir + "-final-sources";
        Directory.CreateDirectory(materializedDirectory);

        CopyTree(corpusRoot, workingRoot);
        try
        {
            if (qualityScanner is not null)
            {
                progress.WriteLine("  quality-diff: capturing shared pristine baseline (dedicated 8.0-all analyzer build)…");
                _qualityBaseline = await qualityScanner.BuildAndScanAsync(
                    workingSln, workingRoot, _build, buildTimeoutSeconds, ct);
                progress.WriteLine(
                    $"  baseline: {_qualityBaseline.SmellTotal} smell(s); CA headline {_qualityBaseline.CaHeadlineTotal}, " +
                    $"all {_qualityBaseline.CaAllTotal}, obsolete {_qualityBaseline.CompilerObsoleteCount} " +
                    $"(CA available={_qualityBaseline.CaAvailable})");
            }

            var fileNo = 0;
            foreach (var filePath in files)
            {
                fileNo++;
                var known = knownByFile.TryGetValue(filePath, out var k) ? k : [];

                if (!File.Exists(filePath))
                {
                    progress.WriteLine($"  [{fileNo}/{files.Count}] [skip] file not found: {filePath}");
                    continue;
                }

                var rel = Path.GetRelativePath(corpusRoot, Path.GetFullPath(filePath));
                if (rel.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(rel))
                {
                    progress.WriteLine($"  [{fileNo}/{files.Count}] [skip] not under corpus root: {filePath}");
                    continue;
                }
                var workingTarget = Path.Combine(workingRoot, rel);

                var content   = await File.ReadAllTextAsync(filePath, ct);
                var estTokens = content.Length / 4;                 // ~4 chars/token heuristic
                var truncated = estTokens > maxInputTokenGuard;

                // Grounded-iterative arm: the opening prompt carries the analyser's Structural finding
                // block for this file; ungrounded arm: null (whole file, no annotation).
                var grounding = groundingByFile is not null && groundingByFile.TryGetValue(filePath, out var gb) ? gb : null;
                var targetDescriptors = known
                    .Select(instance => BlindedTargetDescriptor.Create(
                        instance.SymbolName, instance.Line, instance.EndLine))
                    .ToList();

                LoadedGeneratedTest? visibleTest = null;
                string? workingVisibleProject = null;
                if (visibleTestsByFile is not null && visibleTestsByFile.TryGetValue(filePath, out var loaded))
                {
                    GeneratedTestArtifactLoader.VerifyUnchanged(loaded);
                    if (!Path.GetFullPath(loaded.Artifact.SourceFile)
                            .Equals(filePath, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("visible test was generated for a different source file");
                    if (targetDescriptors.Count != 1 ||
                        !string.Equals(loaded.Artifact.TargetSymbolName, targetDescriptors[0].SymbolName, StringComparison.Ordinal) ||
                        loaded.Artifact.TargetStartLine != targetDescriptors[0].StartLine ||
                        loaded.Artifact.TargetEndLine != targetDescriptors[0].EndLine)
                        throw new InvalidDataException("visible test was generated for a different target declaration");
                    var sourceHash = MaterializedSourceArtifactWriter.Sha256(content);
                    if (!string.Equals(sourceHash, loaded.Artifact.SourceSha256, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException(
                            "visible test was generated from a different pristine source revision");

                    var projectRelative = Path.GetRelativePath(corpusRoot, Path.GetFullPath(loaded.Artifact.ProjectFile));
                    if (projectRelative.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(projectRelative))
                        throw new InvalidDataException("visible-test production project is outside the corpus root");
                    visibleTest = loaded;
                    workingVisibleProject = Path.Combine(workingRoot, projectRelative);
                }

                var systemPrompt = PromptTemplate.BuildAgenticSystemPrompt(iterationBudget, visibleTest is not null);

                progress.WriteLine($"  [{fileNo}/{files.Count}] {Path.GetFileName(filePath)} " +
                                   $"(~{estTokens} tok{(truncated ? ", TRUNCATED-GUARD" : "")}, {known.Count} known" +
                                   $"{(grounding is not null ? ", grounded" : "")}, visible-test=" +
                                   $"{(visibleTest is not null ? "available" : visibleTestsEnabled ? "unavailable" : "disabled")})");

                for (var trajectoryIndex = 1; trajectoryIndex <= runs; trajectoryIndex++)
                {
                    var run = runNumberOffset + trajectoryIndex;
                    ct.ThrowIfCancellationRequested();

                    // Restore the target to pristine so each trajectory starts from the original file.
                    Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
                    File.Copy(filePath, workingTarget, overwrite: true);

                    try
                    {
                        var traj = await RunTrajectoryAsync(
                            systemPrompt, rel.Replace('\\', '/'), content, workingSln, workingTarget,
                            targetDescriptors, grounding, visibleTestsEnabled, visibleTest, workingVisibleProject, ct);

                        var artefactRef = await WriteTrajectoryArtefactAsync(trajectoryDir, rel, run, traj, ct);
                        var materialized = new MaterializedSourceArtifact
                        {
                            ArtifactId = Guid.NewGuid().ToString("N"),
                            Timestamp = DateTimeOffset.UtcNow,
                            Architecture = _architecture,
                            GroundingEnabled = !_performsDetection,
                            ControlStructure = "iterative",
                            VisibleTestsEnabled = traj.VisibleTestsEnabled,
                            VisibleTestAvailable = traj.VisibleTestAvailable,
                            RunNumber = run,
                            RelativeFile = rel.Replace('\\', '/'),
                            SourceSha256 = MaterializedSourceArtifactWriter.Sha256(traj.FinalContent),
                            FinalSource = traj.FinalContent,
                            VisibleTestArtifactRef = traj.VisibleTestArtifactRef,
                            VisibleTestSha256 = traj.VisibleTestSha256,
                            BuildPassed = traj.BuildPassedFinal,
                            VisibleTestPassed = traj.VisibleTestPassedFinal
                        };
                        var materializedRef = await MaterializedSourceArtifactWriter.WriteAsync(
                            materializedDirectory, materialized, ct);

                        // Re-measure reads workingTarget (the final edited state) BEFORE the finally restore.
                        var records = await BuildRecordsAsync(
                            filePath, workingTarget, workingSln, rel.Replace('\\', '/'),
                            known, run, truncated, traj, artefactRef,
                            materializedRef, materialized.SourceSha256, ct);
                        foreach (var rec in records)
                            await runStore.AppendAsync(rec, ct);

                        progress.WriteLine(
                            $"      run {run}: {traj.Iterations} build(s){(traj.BudgetExhausted ? ", BUDGET-EXHAUSTED" : "")}, " +
                            $"{traj.TestAttempts} visible-test run(s), {traj.Findings.Count} finding(s), " +
                            $"final build {(traj.BuildPassedFinal ? "ok" : "FAILED")}");
                    }
                    catch (OperationCanceledException) { throw; }
                    catch (Exception ex)
                    {
                        // One run's failure must not drop the rest of an expensive multi-hour campaign.
                        await Console.Error.WriteLineAsync(
                            $"    [agentic-run-error] {Path.GetFileName(filePath)} run {run}: {ex.Message}");
                    }
                    finally
                    {
                        // Restore the edited file to pristine so it can never contaminate a later file's
                        // whole-solution build or detector re-measure (mirrors RepairVerifier's per-candidate restore).
                        try { File.Copy(filePath, workingTarget, overwrite: true); } catch { /* best effort */ }
                    }
                }
            }
        }
        finally
        {
            TryDeleteTree(workingRoot);
        }
    }

    // ── The autonomous loop ──────────────────────────────────────────────────

    private async Task<Trajectory> RunTrajectoryAsync(
        string systemPrompt, string relForPrompt, string originalContent,
        string workingSln, string workingTarget, IReadOnlyList<BlindedTargetDescriptor> targets,
        string? groundingBlock,
        bool visibleTestsEnabled, LoadedGeneratedTest? visibleTest, string? workingVisibleProject,
        CancellationToken ct)
    {
        var trajectoryStopwatch = Stopwatch.StartNew();
        var baseUserPrompt = groundingBlock is null
            ? PromptTemplate.BuildAgenticUserPrompt(relForPrompt, originalContent, targets)
            : PromptTemplate.BuildGroundedIterativeUserPrompt(
                relForPrompt, originalContent, targets, groundingBlock);
        var visiblePrompt = visibleTest is null ? null : new LoadedVisibleTestPrompt(
            visibleTest.Source.TestName,
            visibleTest.Source.UsingDirectives,
            visibleTest.Source.TestBody,
            visibleTest.Artifact.TestSha256!);
        var userPrompt = PromptTemplate.AppendImmutableVisibleTest(baseUserPrompt, visiblePrompt);
        var promptVersion = PromptTemplate.AgenticPromptVersion(visibleTest is not null);
        var turns      = new List<ChatTurn> { new(ChatRole.User, userPrompt) };
        var builds     = new List<BuildAttempt>();

        var finalContent     = originalContent;  // last applied+built edit (== original if never edited)
        var firstBuildContent = originalContent; // state submitted at the FIRST build (== original if never edited)
        bool? firstBuildOk    = null;            // verdict for the first build (null until the first edit builds)
        bool? firstVisibleTestPassed = null;
        var iterations    = 0;                   // builds performed
        bool? lastBuildOk = null;                // verdict for finalContent's last build
        bool? lastVisibleTestPassed = null;
        var declared      = new List<ParsedAgenticFinding>();
        var inputTokens   = 0;
        var outputTokens  = 0;
        var llmCalls      = 0;
        var testAttempts  = 0;
        var testDurationMs = 0d;
        var parseFailures = 0;
        var completed     = false;
        var parseOk       = true;
        ErrorStatus? error = null;                // non-null ⇒ the trajectory ended on a failure, not on budget
        string? errorMessage = null;

        var maxCalls = iterationBudget + 2;       // slack for a planning/declaration turn beyond the builds
        for (var call = 0; call < maxCalls; call++)
        {
            ct.ThrowIfCancellationRequested();

            LlmResponse response;
            try
            {
                llmCalls++;
                response = await adapter.CompleteAsync(
                    new LlmConversation { SystemPrompt = systemPrompt, Turns = turns, PromptVersion = promptVersion },
                    ct);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                await Console.Error.WriteLineAsync($"    [agentic-error] {relForPrompt}: {ex.Message}");
                parseOk = false;
                error = ClassifyApiError(ex);     // an API failure is NOT budget exhaustion (§4.8.1)
                errorMessage = ex.Message;
                break;
            }

            inputTokens  += response.InputTokens;
            outputTokens += response.OutputTokens;
            turns.Add(new ChatTurn(ChatRole.Assistant, response.Content));

            var parsed = ParseTurn(response.Content);
            if (parsed is null)
            {
                parseFailures++;
                parseOk = false;
                if (parseFailures >= 2)
                {
                    error = ErrorStatus.ParseFailure;   // repeated parse failure is NOT budget exhaustion
                    errorMessage = "two consecutive turns were not valid JSON";
                    break;
                }
                turns.Add(new ChatTurn(ChatRole.User,
                    "Your previous message was not the required JSON object. Respond with ONLY the JSON object described in the instructions."));
                continue;
            }
            parseOk = true;
            parseFailures = 0;

            // Honour the latest declaration, including an explicit empty list (a deliberate retraction).
            // Only an ABSENT findings field leaves an earlier declaration intact.
            if (parsed.FindingsPresent)
                declared = parsed.Findings;

            if (parsed.Action == "complete")
            {
                completed = true;
                break;
            }

            // action == edit_and_build with a non-empty edited_file.
            if (iterations >= iterationBudget)
                break;                            // wants another build but the budget is spent → score the last built state

            bool ok;
            string output;
            try
            {
                await File.WriteAllTextAsync(workingTarget, parsed.EditedFile, ct);
                (ok, output) = await _build(workingSln, buildTimeoutSeconds, ct);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                await Console.Error.WriteLineAsync($"    [agentic-build-error] {relForPrompt}: {ex.Message}");
                error = ErrorStatus.Unknown;      // a write/build-spawn failure is an environment fault, not budget exhaustion
                errorMessage = ex.Message;
                break;
            }

            iterations++;
            finalContent = parsed.EditedFile!;
            lastBuildOk  = ok;
            lastVisibleTestPassed = null;
            if (iterations == 1)                  // freeze the first-build snapshot for the 2×2 single-pass cell
            {
                firstBuildContent = parsed.EditedFile!;
                firstBuildOk      = ok;
            }

            GeneratedTestExecutionResult? visibleResult = null;
            if (ok && visibleTest is not null)
            {
                if (string.IsNullOrWhiteSpace(workingVisibleProject))
                    throw new InvalidDataException("working visible-test project was not resolved");
                testAttempts++;
                var testStopwatch = Stopwatch.StartNew();
                try
                {
                    visibleResult = await _executeVisibleTest(
                        visibleTest.Source, workingVisibleProject, buildTimeoutSeconds, ct);
                    testStopwatch.Stop();
                    testDurationMs += visibleResult.DurationMs;
                    lastVisibleTestPassed = visibleResult.BuildPassed && visibleResult.TestPassed;
                    if (iterations == 1) firstVisibleTestPassed = lastVisibleTestPassed;
                    GeneratedTestArtifactLoader.VerifyUnchanged(visibleTest);
                }
                catch (OperationCanceledException) { throw; }
                catch (Exception ex)
                {
                    testStopwatch.Stop();
                    testDurationMs += testStopwatch.Elapsed.TotalMilliseconds;
                    error = ErrorStatus.Unknown;
                    errorMessage = $"visible-test execution failed: {ex.Message}";
                }
            }

            builds.Add(new BuildAttempt(
                iterations,
                ok,
                Tail(output, 2000),
                lastVisibleTestPassed,
                visibleResult is null ? null : Tail(visibleResult.OutputTail, 2000),
                visibleResult?.DurationMs ?? 0d));

            if (error is not null) break;

            var feedback = PromptTemplate.BuildAgenticBuildFeedback(
                iterations, iterationBudget, ok, Tail(output, 2000));
            feedback += BuildVisibleTestFeedback(visibleResult);
            turns.Add(new ChatTurn(ChatRole.User, feedback));

            if (iterations >= iterationBudget)
                turns.Add(new ChatTurn(ChatRole.User,
                    "You have no build attempts remaining. Respond with action \"complete\" and your final findings."));
        }

        // A no-edit trajectory still has a materialized final state. Execute the admitted visible test
        // once as final-state measurement, but do not feed this post-termination result back to the model.
        if (iterations == 0 && visibleTest is not null)
        {
            if (string.IsNullOrWhiteSpace(workingVisibleProject))
                throw new InvalidDataException("working visible-test project was not resolved");
            testAttempts++;
            var testStopwatch = Stopwatch.StartNew();
            try
            {
                var finalVisibleResult = await _executeVisibleTest(
                    visibleTest.Source, workingVisibleProject, buildTimeoutSeconds, ct);
                testStopwatch.Stop();
                testDurationMs += finalVisibleResult.DurationMs;
                lastVisibleTestPassed = finalVisibleResult.BuildPassed && finalVisibleResult.TestPassed;
                firstVisibleTestPassed = lastVisibleTestPassed;
                GeneratedTestArtifactLoader.VerifyUnchanged(visibleTest);
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception ex)
            {
                testStopwatch.Stop();
                testDurationMs += testStopwatch.Elapsed.TotalMilliseconds;
                error ??= ErrorStatus.Unknown;
                errorMessage ??= $"final visible-test execution failed: {ex.Message}";
            }
        }

        // Budget exhaustion (§4.8.1): the agent did not self-terminate and ran out of build attempts —
        // WITHOUT an API/parse/build error (those are recorded via Error, not as exhaustion).
        var exhausted = error is null && !completed && iterations >= iterationBudget;

        // The working file holds finalContent; it built iff the last edit built, or it was never edited
        // (the pristine corpus file compiles by construction).
        var buildPassedFinal = iterations == 0 || lastBuildOk == true;

        // First-build snapshot: the pristine file compiles by construction when nothing was edited;
        // otherwise its build is the recorded verdict of the first edit.
        var firstBuildPassed = iterations == 0 || firstBuildOk == true;

        trajectoryStopwatch.Stop();
        return new Trajectory(
            relForPrompt, systemPrompt, userPrompt, promptVersion, turns, builds, finalContent,
            iterations, exhausted, parseOk, buildPassedFinal, declared, inputTokens, outputTokens,
            llmCalls, testAttempts, testDurationMs, trajectoryStopwatch.Elapsed.TotalMilliseconds,
            visibleTestsEnabled, visibleTest is not null, visibleTest?.Artifact.ArtifactRef,
            visibleTest?.Artifact.TestSha256, lastVisibleTestPassed,
            error, errorMessage, firstBuildContent, firstBuildPassed, firstVisibleTestPassed);
    }

    private static string BuildVisibleTestFeedback(GeneratedTestExecutionResult? result)
    {
        if (result is null) return string.Empty;
        var passed = result.BuildPassed && result.TestPassed;
        return passed
            ? "\n\n## Immutable visible characterization test: PASS\n" +
              "The edited production code preserves the behaviour exercised by this test."
            : "\n\n## Immutable visible characterization test: FAIL\n```\n" +
              Tail(result.OutputTail, 2000) + "\n```\n" +
              "Revise only the production code so the frozen test passes; do not rewrite, weaken, bypass, or work around the test.";
    }

    // ── Record construction ────────────────────────────────────────────────

    private async Task<List<RunRecord>> BuildRecordsAsync(
        string filePath, string workingTarget, string workingSln, string relFile,
        List<KnownInstance> known, int runNumber, bool truncated,
        Trajectory traj, string artefactRef, string materializedRef, string materializedHash,
        CancellationToken ct)
    {
        var timestamp = DateTimeOffset.UtcNow;
        var records   = new List<RunRecord>();
        var matchedKeys = new HashSet<string>(StringComparer.Ordinal);

        // 1. Diagnosis finding rows — only the target-only arm must infer and report the anti-pattern. The grounded
        //    arm is supplied the findings (relieved of detection), so it writes no detection rows (§4.4.1).
        if (_performsDetection)
            foreach (var f in traj.Findings)
            {
                var match = Match(f, known);
                if (match is not null) matchedKeys.Add(match.InstanceKey);
                records.Add(FindingRecord(
                    filePath, f, match, runNumber, timestamp, truncated, traj, artefactRef,
                    materializedRef, materializedHash));
            }

        if (known.Count == 0) return records;

        // 2a. FINAL snapshot — score the agent's final edited solution (workingTarget already holds it).
        var finalScores = new Dictionary<string, SnapshotScore>(StringComparer.Ordinal);
        foreach (var inst in known)
        {
            ct.ThrowIfCancellationRequested();
            finalScores[inst.InstanceKey] = await ScoreSnapshotAsync(inst, traj.BuildPassedFinal, workingTarget, ct);
        }

        // 2a′. Whole-solution quality impact of the agent's FINAL state (the state a developer would ship).
        //      Measured once per trajectory via a dedicated analyzer build while workingTarget still holds
        //      finalContent — BEFORE the first-build snapshot overwrites it below. Only the final rows carry it.
        SolutionQualityScan? finalAfterScan = null;
        if (qualityScanner is not null && _qualityBaseline is not null && traj.BuildPassedFinal)
        {
            var workingRoot = Path.GetDirectoryName(workingSln)!;
            finalAfterScan = await qualityScanner.BuildAndScanAsync(
                workingSln, workingRoot, _build, buildTimeoutSeconds, ct);
        }

        // 2b. FIRST-BUILD snapshot — the single-pass cell of the 2×2 (§4.4.1): the state submitted at the
        //     first build, before any compiler feedback. Re-score that frozen state with the SAME detector.
        //     Write it back to the working file first so the detector (and its semantic model) sees it; a
        //     first build that failed never reaches re-measure (it ladders to build_fails below).
        if (traj.FirstBuildPassed)
            await File.WriteAllTextAsync(workingTarget, traj.FirstBuildContent, ct);
        var firstScores = new Dictionary<string, SnapshotScore>(StringComparer.Ordinal);
        foreach (var inst in known)
        {
            ct.ThrowIfCancellationRequested();
            firstScores[inst.InstanceKey] = await ScoreSnapshotAsync(inst, traj.FirstBuildPassed, workingTarget, ct);
        }

        // 3. Emit one verified-repair row per (instance × snapshot).
        foreach (var inst in known)
        {
            var recovered = !_performsDetection || matchedKeys.Contains(inst.InstanceKey);

            var fin = finalScores[inst.InstanceKey];
            var finalDelta = finalAfterScan is not null
                ? QualityDelta.Between(_qualityBaseline!, finalAfterScan, inst.Type, relFile)
                : null;
            records.Add(VerifiedRecord(inst, runNumber, timestamp, truncated, traj, artefactRef,
                materializedRef, materializedHash,
                fin.BuildPassed, fin.Metrics, fin.Ladder, recovered, snapshot: "final", qualityDelta: finalDelta));

            var fb = firstScores[inst.InstanceKey];
            records.Add(VerifiedRecord(inst, runNumber, timestamp, truncated, traj, artefactRef,
                materializedRef, materializedHash,
                fb.BuildPassed, fb.Metrics, fb.Ladder, recovered, snapshot: "first_build"));
        }

        return records;
    }

    private readonly record struct SnapshotScore(
        bool? BuildPassed, IReadOnlyDictionary<string, double>? Metrics, VerifiedRepairOutcome Ladder);

    /// <summary>
    /// Scores one trajectory snapshot against a seeded instance: build gate then, on a green build,
    /// detector re-run (§4.5.1). A snapshot whose build failed ladders to <c>build_fails</c> without
    /// re-measuring; the caller must have written the snapshot's source to <paramref name="fileToMeasure"/>.
    /// </summary>
    private async Task<SnapshotScore> ScoreSnapshotAsync(
        KnownInstance inst, bool buildPassed, string fileToMeasure, CancellationToken ct)
    {
        if (!buildPassed)
            return new SnapshotScore(false, null, VerifiedRepairOutcome.BuildFails);

        var remeasure = await measurer.RemeasureAsync(inst.Type, fileToMeasure, inst.SymbolName, ct);
        var ladder    = remeasure.StillTriggers ? VerifiedRepairOutcome.BuildsUnresolved : VerifiedRepairOutcome.Resolved;
        var metrics   = remeasure.StillTriggers ? remeasure.Metrics : null;
        return new SnapshotScore(true, metrics, ladder);
    }

    private RunRecord FindingRecord(
        string filePath, ParsedAgenticFinding f, KnownInstance? match,
        int runNumber, DateTimeOffset timestamp, bool truncated, Trajectory traj, string artefactRef,
        string materializedRef, string materializedHash)
    {
        var isSpurious = match is null;
        var type = match?.Type ?? NormaliseType(f.AntiPattern) ?? AntiPatternType.GodClass;
        var rawCombined = $"{f.Explanation}\n{f.QualityImpact}\n{f.Remediation}";
        var mentioned = QualityAttributeExtraction.ExtractMentioned(rawCombined);
        var expected  = QualityAttributeMap.ForType(type);
        var alignment = QualityAttributeExtraction.ComputeAlignment(parsedOk: true, expected, mentioned);

        return new RunRecord
        {
            RunId             = Guid.NewGuid().ToString("N"),
            Timestamp         = timestamp,
            RunNumber         = runNumber,
            AntiPatternType   = type,
            FilePath          = filePath,
            SymbolName        = match?.SymbolName ?? f.Symbol ?? "<unknown>",
            Line              = match?.Line ?? f.Line,
            Severity          = match?.Severity ?? Severity.Warning,
            Snippet           = match?.Snippet,
            Metrics           = null,
            ContextLevel      = _performsDetection ? ContextLevel.Minimal : ContextLevel.Structural,
            ModelName         = modelName,
            PromptVersion     = traj.PromptVersion,
            Architecture      = _architecture,
            GroundingEnabled  = !_performsDetection,
            ControlStructure  = "iterative",
            VisibleTestsEnabled = traj.VisibleTestsEnabled,
            VisibleTestAvailable = traj.VisibleTestAvailable,
            VisibleTestArtifactRef = traj.VisibleTestArtifactRef,
            VisibleTestSha256 = traj.VisibleTestSha256,
            VisibleTestPassed = traj.VisibleTestPassedFinal,
            LlmCallCount      = traj.LlmCalls,
            BuildAttemptCount = traj.Iterations,
            TestAttemptCount  = traj.TestAttempts,
            TestDurationMs    = traj.TestDurationMs,
            MaterializedSourceRef = materializedRef,
            MaterializedSourceSha256 = materializedHash,
            LlmReportedSymbol = f.Symbol,
            LlmReportedLine   = f.Line,
            LlmReportedAntiPattern = f.AntiPattern,    // the agent's raw type label (match is location-based, §4.5.1)
            MatchedInstanceId = match?.InstanceKey,
            IsSpurious        = isSpurious,
            ContextTruncated  = truncated,
            RawSystemPrompt   = traj.SystemPrompt,
            RawUserPrompt     = traj.UserPrompt,
            RawLlmOutput      = LastAssistant(traj),
            InputTokens       = traj.InputTokens,
            OutputTokens      = traj.OutputTokens,
            DurationMs        = traj.DurationMs,
            ParsedExplanation = f.Explanation,
            ParsedQualityImpact = string.IsNullOrWhiteSpace(f.QualityImpact) ? null : f.QualityImpact,
            ParsedSuggestedFix  = f.Remediation,
            ParsedRisks         = null,
            ExpectedQualityAttributes     = expected,
            LlmQualityAttributesMentioned = mentioned,
            QualityAttributeAlignment     = alignment,
            AgenticIterations      = traj.Iterations,
            AgenticBudgetExhausted = traj.BudgetExhausted,
            AgenticTrajectoryRef   = artefactRef,
            ParseStatus       = traj.ParseOk ? ParseStatus.Ok : ParseStatus.Failed,
            ErrorStatus       = traj.Error,
            ErrorMessage      = traj.ErrorMessage
        };
    }

    private RunRecord VerifiedRecord(
        KnownInstance inst, int runNumber, DateTimeOffset timestamp, bool truncated, Trajectory traj,
        string artefactRef, string materializedRef, string materializedHash,
        bool? buildPassed, IReadOnlyDictionary<string, double>? remeasured,
        VerifiedRepairOutcome ladder, bool recovered, string snapshot, QualityDelta? qualityDelta = null)
        => new()
        {
            RunId             = Guid.NewGuid().ToString("N"),
            Timestamp         = timestamp,
            RunNumber         = runNumber,
            AntiPatternType   = inst.Type,
            FilePath          = inst.FilePath,
            SymbolName        = inst.SymbolName,
            Line              = inst.Line,
            Severity          = inst.Severity,
            Snippet           = inst.Snippet,
            Metrics           = null,
            ContextLevel      = _performsDetection ? ContextLevel.Minimal : ContextLevel.Structural,
            ModelName         = modelName,
            PromptVersion     = traj.PromptVersion,
            Architecture      = _architecture,
            GroundingEnabled  = !_performsDetection,
            ControlStructure  = "iterative",
            VisibleTestsEnabled = traj.VisibleTestsEnabled,
            VisibleTestAvailable = traj.VisibleTestAvailable,
            VisibleTestArtifactRef = traj.VisibleTestArtifactRef,
            VisibleTestSha256 = traj.VisibleTestSha256,
            VisibleTestPassed = snapshot == "first_build"
                ? traj.FirstVisibleTestPassed
                : traj.VisibleTestPassedFinal,
            LlmCallCount      = traj.LlmCalls,
            BuildAttemptCount = traj.Iterations,
            TestAttemptCount  = traj.TestAttempts,
            TestDurationMs    = traj.TestDurationMs,
            MaterializedSourceRef = materializedRef,
            MaterializedSourceSha256 = materializedHash,
            ContextTruncated  = truncated,
            RawSystemPrompt   = traj.SystemPrompt,
            RawUserPrompt     = traj.UserPrompt,
            RawLlmOutput      = LastAssistant(traj),
            InputTokens       = traj.InputTokens,
            OutputTokens      = traj.OutputTokens,
            DurationMs        = traj.DurationMs,
            // Verified-repair: the agent's own final solution is the repair (no separate applier, §4.7.1).
            ApplierModel             = null,
            ApplierPromptVersion     = null,
            RepairApplicable         = true,            // an agentic trajectory always produces source
            RepairUnapplicableReason = null,
            BuildPassed              = buildPassed,
            RemeasuredMetrics        = remeasured,
            VerifiedRepairLadder     = ladder,
            VerifiedRepairSuccess    = ladder == VerifiedRepairOutcome.Resolved,
            QualityDelta             = qualityDelta,
            AgenticIterations      = traj.Iterations,
            AgenticBudgetExhausted = traj.BudgetExhausted,
            AgenticTrajectoryRef   = artefactRef,
            AgenticRecovered       = recovered,
            AgenticSnapshot        = snapshot,
            ParseStatus       = traj.ParseOk ? ParseStatus.Ok : ParseStatus.Failed,
            ErrorStatus       = traj.Error,
            ErrorMessage      = traj.ErrorMessage
        };

    private static string? LastAssistant(Trajectory traj)
        => traj.Turns.LastOrDefault(t => t.Role == ChatRole.Assistant)?.Content;

    // ── Matching (§4.5.1) ──────────────────────────────────────────────────
    //
    // The thesis match rule is LOCATION-ONLY: "a reported finding matches a seeded instance when its
    // symbol, method, or line range overlaps the recorded location" (§4.4.1/§4.5.1). The agent's reported
    // anti-pattern TYPE does not gate the match — a correctly-localised finding with a wrong/garbled type
    // must not be scored as both a recall miss and a spurious false positive. When the reported type is
    // recognised it only breaks ties toward a same-type instance; otherwise any overlapping instance matches.

    private static KnownInstance? Match(ParsedAgenticFinding f, List<KnownInstance> known)
    {
        var reportedType = NormaliseType(f.AntiPattern);   // may be null (missing/garbled label)
        KnownInstance? locationMatch = null;

        foreach (var k in known)
        {
            var lineInRange   = f.Line >= k.Line && f.Line <= k.EndLine;
            var symbolOverlap = SimpleNameOverlap(f.Symbol, k.SymbolName);
            if (!lineInRange && !symbolOverlap) continue;  // location overlap is the match rule

            if (reportedType is not null && k.Type == reportedType)
                return k;                                  // best: location overlap AND same reported type
            locationMatch ??= k;                           // fallback: location overlap regardless of type
        }
        return locationMatch;
    }

    private static bool SimpleNameOverlap(string? a, string? b)
    {
        var sa = SimpleName(a);
        var sb = SimpleName(b);
        if (sa.Length == 0 || sb.Length == 0) return false;
        return sa.Contains(sb, StringComparison.OrdinalIgnoreCase)
            || sb.Contains(sa, StringComparison.OrdinalIgnoreCase);
    }

    private static string SimpleName(string? symbol)
    {
        if (string.IsNullOrWhiteSpace(symbol)) return string.Empty;
        var s = symbol.Trim();
        var paren = s.IndexOf('(');
        if (paren >= 0) s = s[..paren];
        var dot = s.LastIndexOf('.');
        if (dot >= 0 && dot < s.Length - 1) s = s[(dot + 1)..];
        var arrow = s.IndexOf('→');
        if (arrow >= 0) s = s[(arrow + 1)..].Trim();
        return s;
    }

    private static AntiPatternType? NormaliseType(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        var t = raw.Replace(" ", "").Replace("_", "").Replace("-", "").ToLowerInvariant();
        return t switch
        {
            "godclass"                          => AntiPatternType.GodClass,
            "longmethod"                        => AntiPatternType.LongMethod,
            "obsoleteapiusage" or "obsoleteapi" => AntiPatternType.ObsoleteApiUsage,
            _                                   => null
        };
    }

    // ── Per-turn JSON parsing ────────────────────────────────────────────────

    private readonly record struct ParsedAgenticFinding(
        string? AntiPattern, string? Symbol, int Line,
        string Explanation, string QualityImpact, string Remediation);

    /// <param name="FindingsPresent">Whether the turn carried a "findings" array at all — distinguishes a
    /// deliberate empty list (a retraction, which overwrites) from an absent field (which leaves the prior set).</param>
    private sealed record ParsedTurn(string Action, string? EditedFile, List<ParsedAgenticFinding> Findings, bool FindingsPresent);

    private static ParsedTurn? ParseTurn(string content)
    {
        try
        {
            var json = content.Trim();
            if (json.StartsWith("```"))
            {
                json = string.Join('\n', json.Split('\n').Skip(1));
                var fence = json.LastIndexOf("```", StringComparison.Ordinal);
                if (fence >= 0) json = json[..fence].Trim();
            }

            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind != JsonValueKind.Object) return null;
            var root = doc.RootElement;

            var action = root.TryGetProperty("action", out var a) && a.ValueKind == JsonValueKind.String
                ? a.GetString() ?? ""
                : "";
            action = action.Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");
            if (action is not ("edit_and_build" or "complete")) return null;

            if (!root.TryGetProperty("edited_file", out var e) || e.ValueKind != JsonValueKind.String) return null;
            var edited = e.GetString() ?? string.Empty;
            if (action == "edit_and_build" && string.IsNullOrWhiteSpace(edited)) return null;
            if (action == "complete" && edited.Length != 0) return null;

            var findings = new List<ParsedAgenticFinding>();
            var findingsPresent = root.TryGetProperty("findings", out var fs) && fs.ValueKind == JsonValueKind.Array;
            if (findingsPresent)
                foreach (var el in fs.EnumerateArray())
                    if (TryParseFinding(el, out var pf)) findings.Add(pf);

            return new ParsedTurn(action, edited, findings, findingsPresent);
        }
        catch
        {
            return null;
        }
    }

    private static string ValidateArchitecture(string value) =>
        value switch
        {
            "agentic" => value,
            "grounded_iterative" => value,
            _ => throw new ArgumentOutOfRangeException(
                "architecture", value, "architecture must be 'agentic' or 'grounded_iterative'")
        };

    private static bool TryParseFinding(JsonElement el, out ParsedAgenticFinding finding)
    {
        finding = default;
        if (el.ValueKind != JsonValueKind.Object) return false;

        var ap = el.TryGetProperty("anti_pattern", out var a) ? a.GetString() : null;

        string? symbol = null;
        var line = 0;
        if (el.TryGetProperty("location", out var loc) && loc.ValueKind == JsonValueKind.Object)
        {
            symbol = loc.TryGetProperty("symbol", out var s) ? s.GetString() : null;
            if (loc.TryGetProperty("line", out var ln) && ln.TryGetInt32(out var lv)) line = lv;
        }

        finding = new ParsedAgenticFinding(
            ap, symbol, line,
            el.TryGetProperty("explanation",    out var ex) ? ex.GetString() ?? "" : "",
            el.TryGetProperty("quality_impact", out var q)  ? q.GetString()  ?? "" : "",
            el.TryGetProperty("remediation",    out var r)  ? r.GetString()  ?? "" : "");
        return true;
    }

    // ── Trajectory artefact (frozen for reproducibility, §4.8.5) ─────────────

    private sealed record BuildAttempt(
        int Attempt,
        bool Ok,
        string OutputTail,
        bool? VisibleTestPassed,
        string? VisibleTestOutputTail,
        double TestDurationMs);

    private sealed record Trajectory(
        string RelPath, string SystemPrompt, string UserPrompt, string PromptVersion,
        IReadOnlyList<ChatTurn> Turns, IReadOnlyList<BuildAttempt> Builds,
        string FinalContent, int Iterations, bool BudgetExhausted, bool ParseOk,
        bool BuildPassedFinal, IReadOnlyList<ParsedAgenticFinding> Findings,
        int InputTokens, int OutputTokens,
        int LlmCalls, int TestAttempts, double TestDurationMs, double DurationMs,
        bool VisibleTestsEnabled, bool VisibleTestAvailable,
        string? VisibleTestArtifactRef, string? VisibleTestSha256, bool? VisibleTestPassedFinal,
        ErrorStatus? Error, string? ErrorMessage,
        string FirstBuildContent, bool FirstBuildPassed, bool? FirstVisibleTestPassed);

    private async Task<string> WriteTrajectoryArtefactAsync(
        string trajectoryDir, string rel, int run, Trajectory traj, CancellationToken ct)
    {
        var safe = rel.Replace('\\', '_').Replace('/', '_');
        var path = Path.Combine(trajectoryDir, $"{safe}__run{run}.json");

        var artefact = new
        {
            file             = traj.RelPath,
            run,
            architecture     = _architecture,
            model            = modelName,
            prompt_version   = traj.PromptVersion,
            iteration_budget = iterationBudget,
            iterations       = traj.Iterations,
            llm_calls        = traj.LlmCalls,
            build_attempts   = traj.Iterations,
            test_attempts    = traj.TestAttempts,
            test_duration_ms = traj.TestDurationMs,
            duration_ms      = traj.DurationMs,
            budget_exhausted = traj.BudgetExhausted,
            parse_ok         = traj.ParseOk,
            error            = traj.Error?.ToString(),
            error_message    = traj.ErrorMessage,
            build_passed_final = traj.BuildPassedFinal,
            visible_tests_enabled = traj.VisibleTestsEnabled,
            visible_test_available = traj.VisibleTestAvailable,
            visible_test_artifact_ref = traj.VisibleTestArtifactRef,
            visible_test_sha256 = traj.VisibleTestSha256,
            visible_test_passed_final = traj.VisibleTestPassedFinal,
            first_build_passed = traj.FirstBuildPassed,
            first_visible_test_passed = traj.FirstVisibleTestPassed,
            first_build_source = traj.FirstBuildContent,
            system_prompt    = traj.SystemPrompt,
            turns            = traj.Turns.Select(t => new { role = t.Role.ToString().ToLowerInvariant(), content = t.Content }),
            builds           = traj.Builds.Select(b => new
            {
                attempt = b.Attempt,
                ok = b.Ok,
                output = b.OutputTail,
                visible_test_passed = b.VisibleTestPassed,
                visible_test_output = b.VisibleTestOutputTail,
                test_duration_ms = b.TestDurationMs
            }),
            declared_findings = traj.Findings.Select(f => new
            {
                anti_pattern = f.AntiPattern, symbol = f.Symbol, line = f.Line,
                explanation = f.Explanation, quality_impact = f.QualityImpact, remediation = f.Remediation
            }),
            final_source     = traj.FinalContent
        };

        var jsonOpts = new JsonSerializerOptions { WriteIndented = true };
        await File.WriteAllTextAsync(path, JsonSerializer.Serialize(artefact, jsonOpts), new UTF8Encoding(false), ct);
        return Path.GetFullPath(path);
    }

    // ── Working-copy helpers (mirror RepairVerifier) ─────────────────────────

    private void CopyTree(string src, string dst)
    {
        src = Path.GetFullPath(src);
        Directory.CreateDirectory(dst);
        foreach (var file in Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(src, file);
            if (IsSkipped(rel)) continue;
            var target = Path.Combine(dst, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }

    private bool IsSkipped(string relativePath)
        => relativePath
            .Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries)
            .Any(part => _skipDirs.Contains(part, StringComparer.OrdinalIgnoreCase));

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { /* best effort — temp dir */ }
    }

    private static string Tail(string s, int maxChars)
        => s.Length <= maxChars ? s : s[^maxChars..];

    private static ErrorStatus ClassifyApiError(Exception ex)
    {
        var msg = ex.Message?.ToLowerInvariant() ?? string.Empty;
        if (msg.Contains("token") && (msg.Contains("limit") || msg.Contains("exceeded") || msg.Contains("truncat")))
            return ErrorStatus.TokenLimitTruncation;
        if (msg.Contains("empty") || msg.Contains("no content"))
            return ErrorStatus.EmptyResponse;
        return ErrorStatus.ApiFailure;
    }
}
