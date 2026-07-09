using System.Diagnostics;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Objective repair verification (§4.5.1, §4.7.1). For each repair candidate:
/// apply it strict-literally with the Claude applier → write it into a working copy of the corpus
/// → <c>dotnet build</c> (hard gate) → re-run the detector and re-measure the triggering metric.
/// The outcome is recorded both as an ordinal ladder
/// (<see cref="VerifiedRepairOutcome"/>) and the binary headline <c>verified_repair_success</c>.
///
/// The frozen corpus is never mutated: the tree is copied once to a temp working directory, and
/// each candidate's edit is written then restored so candidates do not interfere. Runs sequentially.
/// </summary>
public sealed class RepairVerifier(
    RepairApplier applier,
    IRepairMeasurer measurer,
    string solutionPath,
    int buildTimeoutSeconds,
    Func<string, int, CancellationToken, Task<(bool Ok, string Output)>>? build = null,
    ISolutionQualityScanner? qualityScanner = null)
{
    private static readonly string[] SkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];

    /// <summary>The build gate. Defaults to a real <c>dotnet build</c>; overridable for tests.</summary>
    private readonly Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> _build
        = build ?? DotnetBuilder.BuildAsync;

    /// <summary>Shared pristine-corpus quality baseline (the "before" for every candidate), captured once when <c>--quality-diff</c> is on.</summary>
    private SolutionQualityScan? _qualityBaseline;

    public async Task RunAsync(
        IReadOnlyList<RepairCandidate> candidates,
        IRunStore store,
        TextWriter progress,
        CancellationToken cancellationToken)
    {
        var corpusRoot  = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-verify-{Guid.NewGuid():N}");
        var workingSln  = Path.Combine(workingRoot, Path.GetFileName(solutionPath));

        progress.WriteLine(
            $"verify-repair: {candidates.Count} candidate(s), applier={applier.Model} " +
            $"(prompt {applier.PromptVersion}), solution={Path.GetFileName(solutionPath)}");
        progress.WriteLine($"  working copy: {workingRoot}");

        CopyTree(corpusRoot, workingRoot);
        try
        {
            if (qualityScanner is not null)
            {
                progress.WriteLine("  quality-diff: capturing shared pristine baseline (dedicated 8.0-all analyzer build)…");
                _qualityBaseline = await qualityScanner.BuildAndScanAsync(
                    workingSln, workingRoot, _build, buildTimeoutSeconds, cancellationToken);
                progress.WriteLine(
                    $"  baseline: {_qualityBaseline.SmellTotal} smell(s); CA headline {_qualityBaseline.CaHeadlineTotal}, " +
                    $"all {_qualityBaseline.CaAllTotal}, obsolete {_qualityBaseline.CompilerObsoleteCount} " +
                    $"(CA available={_qualityBaseline.CaAvailable})");
            }

            var n = 0;
            foreach (var candidate in candidates)
            {
                cancellationToken.ThrowIfCancellationRequested();
                n++;
                var record = await VerifyOneAsync(candidate, corpusRoot, workingRoot, workingSln, cancellationToken);
                await store.AppendAsync(record, cancellationToken);

                var outcome = record.VerifiedRepairLadder?.ToString()
                              ?? record.ErrorStatus?.ToString()
                              ?? "error";
                progress.WriteLine(
                    $"  [{n}/{candidates.Count}] {record.AntiPatternType} {Shorten(candidate.SymbolName)} " +
                    $"[{candidate.Architecture}/{candidate.ContextLevel}/{candidate.ModelName} run{candidate.RunNumber}] → {outcome}");
            }
        }
        finally
        {
            TryDeleteTree(workingRoot);
        }
    }

    private async Task<RunRecord> VerifyOneAsync(
        RepairCandidate c, string corpusRoot, string workingRoot, string workingSln, CancellationToken ct)
    {
        var timestamp = DateTimeOffset.UtcNow;
        var sw = Stopwatch.StartNew();

        var originalFull = Path.GetFullPath(c.FilePath);
        var rel = Path.GetRelativePath(corpusRoot, originalFull);
        if (rel.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(rel))
        {
            sw.Stop();
            return ErrorRecord(c, timestamp, sw.Elapsed.TotalMilliseconds,
                ErrorStatus.UnsupportedFile,
                $"file is not under the corpus solution root ({corpusRoot})");
        }

        if (!File.Exists(originalFull))
        {
            sw.Stop();
            return ErrorRecord(c, timestamp, sw.Elapsed.TotalMilliseconds,
                ErrorStatus.UnsupportedFile, $"source file not found: {originalFull}");
        }

        var workingTarget  = Path.Combine(workingRoot, rel);
        var originalSource  = await File.ReadAllTextAsync(originalFull, ct);
        var relForPrompt    = rel.Replace('\\', '/');

        // 1. Apply (strict-literal Claude applier).
        ApplierResult apply;
        try
        {
            apply = await applier.ApplyAsync(c, originalSource, relForPrompt, ct);
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            sw.Stop();
            await Console.Error.WriteLineAsync($"    [applier-error] {Shorten(c.SymbolName)}: {ex.Message}");
            return ErrorRecord(c, timestamp, sw.Elapsed.TotalMilliseconds, ErrorStatus.ApiFailure, ex.Message);
        }

        // 2. Unapplicable — vague repair, applier declined, or unparseable applier output.
        if (!apply.Applicable)
        {
            sw.Stop();
            var reason = apply.ParseOk
                ? apply.Reason ?? "applier marked the repair unapplicable"
                : "applier output could not be parsed";
            return BuildRecord(c, timestamp, sw.Elapsed.TotalMilliseconds, apply,
                applicable: false, unapplicableReason: reason,
                buildPassed: null, remeasured: null,
                ladder: VerifiedRepairOutcome.Unapplicable,
                parseStatus: apply.ParseOk ? ParseStatus.Ok : ParseStatus.Failed,
                errorStatus: apply.ParseOk ? null : ErrorStatus.ParseFailure,
                errorMessage: apply.ParseOk ? null : "applier output parse failed");
        }

        // 3. Materialise into the working copy and build (HARD GATE), then re-measure.
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
            await File.WriteAllTextAsync(workingTarget, apply.EditedFile!, ct);

            var (built, buildOutput) = await _build(workingSln, buildTimeoutSeconds, ct);
            if (!built)
            {
                sw.Stop();
                return BuildRecord(c, timestamp, sw.Elapsed.TotalMilliseconds, apply,
                    applicable: true, unapplicableReason: null,
                    buildPassed: false, remeasured: null,
                    ladder: VerifiedRepairOutcome.BuildFails,
                    parseStatus: ParseStatus.Ok, errorStatus: null,
                    errorMessage: Tail(buildOutput, 2000));
            }

            var remeasure = await measurer.RemeasureAsync(c.Type, workingTarget, c.SymbolName, ct);
            var ladder = remeasure.StillTriggers
                ? VerifiedRepairOutcome.BuildsUnresolved
                : VerifiedRepairOutcome.Resolved;

            sw.Stop();
            var durationMs = sw.Elapsed.TotalMilliseconds;   // timed BEFORE the quality build so the instrument does not inflate repair timing

            // Whole-solution quality impact: the build gate passed, so a meaningful "after" state exists.
            // A dedicated analyzer build (workingTarget still holds the applied source) emits the SARIF the
            // scanner reads; the delta is against the shared pristine baseline.
            QualityDelta? qualityDelta = null;
            if (qualityScanner is not null && _qualityBaseline is not null)
            {
                var afterScan = await qualityScanner.BuildAndScanAsync(
                    workingSln, workingRoot, _build, buildTimeoutSeconds, ct);
                qualityDelta = QualityDelta.Between(_qualityBaseline, afterScan, c.Type, rel.Replace('\\', '/'));
            }

            return BuildRecord(c, timestamp, durationMs, apply,
                applicable: true, unapplicableReason: null,
                buildPassed: true,
                remeasured: remeasure.StillTriggers ? remeasure.Metrics : null,
                ladder: ladder,
                parseStatus: ParseStatus.Ok, errorStatus: null, errorMessage: null,
                qualityDelta: qualityDelta);
        }
        finally
        {
            // Restore the working file to pristine so the next candidate starts clean.
            try { File.Copy(originalFull, workingTarget, overwrite: true); } catch { /* best effort */ }
        }
    }

    // ── Record construction ─────────────────────────────────────────────────────

    private RunRecord BuildRecord(
        RepairCandidate c, DateTimeOffset timestamp, double durationMs, ApplierResult apply,
        bool applicable, string? unapplicableReason, bool? buildPassed,
        IReadOnlyDictionary<string, double>? remeasured, VerifiedRepairOutcome ladder,
        ParseStatus parseStatus, ErrorStatus? errorStatus, string? errorMessage,
        QualityDelta? qualityDelta = null)
        => new()
        {
            RunId                    = Guid.NewGuid().ToString("N"),
            Timestamp                = timestamp,
            RunNumber                = c.RunNumber,
            AntiPatternType          = c.Type,
            FilePath                 = c.FilePath,
            SymbolName               = c.SymbolName,
            Line                     = c.Line,
            Severity                 = c.Severity,
            Snippet                  = c.Snippet,
            Metrics                  = c.Metrics,
            ContextLevel             = c.ContextLevel,
            ModelName                = c.ModelName,
            PromptVersion            = c.PromptVersion,
            Architecture             = c.Architecture,
            RawSystemPrompt          = apply.SystemPrompt,
            RawUserPrompt            = apply.UserPrompt,
            RawLlmOutput             = apply.RawOutput,
            InputTokens              = apply.InputTokens,
            OutputTokens             = apply.OutputTokens,
            DurationMs               = durationMs,
            ParsedSuggestedFix       = c.RepairText,
            SourceRunId              = c.SourceRunId,
            ApplierModel             = applier.Model,
            ApplierPromptVersion     = applier.PromptVersion,
            RepairApplicable         = applicable,
            RepairUnapplicableReason = unapplicableReason,
            BuildPassed              = buildPassed,
            RemeasuredMetrics        = remeasured,
            VerifiedRepairLadder     = ladder,
            VerifiedRepairSuccess    = ladder == VerifiedRepairOutcome.Resolved,
            QualityDelta             = qualityDelta,
            ParseStatus              = parseStatus,
            ErrorStatus              = errorStatus,
            ErrorMessage             = errorMessage
        };

    private RunRecord ErrorRecord(
        RepairCandidate c, DateTimeOffset timestamp, double durationMs,
        ErrorStatus errorStatus, string errorMessage)
        => new()
        {
            RunId                = Guid.NewGuid().ToString("N"),
            Timestamp            = timestamp,
            RunNumber            = c.RunNumber,
            AntiPatternType      = c.Type,
            FilePath             = c.FilePath,
            SymbolName           = c.SymbolName,
            Line                 = c.Line,
            Severity             = c.Severity,
            Snippet              = c.Snippet,
            Metrics              = c.Metrics,
            ContextLevel         = c.ContextLevel,
            ModelName            = c.ModelName,
            PromptVersion        = c.PromptVersion,
            Architecture         = c.Architecture,
            RawSystemPrompt      = HybridLens.ContextBuilder.PromptTemplate.ApplierSystemPrompt,
            RawUserPrompt        = string.Empty,
            RawLlmOutput         = null,
            DurationMs           = durationMs,
            ParsedSuggestedFix   = c.RepairText,
            SourceRunId          = c.SourceRunId,
            ApplierModel         = applier.Model,
            ApplierPromptVersion = applier.PromptVersion,
            ParseStatus          = ParseStatus.NotAttempted,
            ErrorStatus          = errorStatus,
            ErrorMessage         = errorMessage
        };

    // ── Working-copy helpers ──────────────────────────────────────────────────

    private static void CopyTree(string src, string dst)
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

    private static bool IsSkipped(string relativePath)
        => relativePath
            .Split(['\\', '/'], StringSplitOptions.RemoveEmptyEntries)
            .Any(part => SkipDirs.Contains(part, StringComparer.OrdinalIgnoreCase));

    private static void TryDeleteTree(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); }
        catch { /* best effort — temp dir */ }
    }

    private static string Tail(string s, int maxChars)
        => s.Length <= maxChars ? s : s[^maxChars..];

    private static string Shorten(string symbol)
        => symbol.Length <= 60 ? symbol : "…" + symbol[^59..];
}
