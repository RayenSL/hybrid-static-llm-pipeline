using System.Diagnostics;
using System.Text;
using System.Text.Json;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;

namespace HybridLens.Pipeline;

/// <summary>
/// Runs the agentic architecture arm (§4.4.1, Appendix E prompt v2.0.0). Unlike the single-shot
/// LLM-only arm it replaced, the agent works in an AUTONOMOUS LOOP over a whole, unannotated source
/// FILE: each turn it either edits the file and requests a build, or declares completion. Its only
/// tool is the compiler — after every edit the pipeline builds a working copy of the corpus and
/// feeds the result (success or diagnostics) back as the next user turn — and it is never shown the
/// static analyser, so the arm stays ungrounded. The loop ends when the agent declares completion
/// or the frozen iteration budget is exhausted (a distinct outcome, §4.8.1).
///
/// Two row types are written per (file × run):
///   • detection finding rows — one per reported finding, matched to the known instances by
///     type + line-in-range OR simple-symbol overlap (§4.5.1), feeding recall and precision; and
///   • verified-repair rows — one per known instance in the file, scoring the agent's FINAL edited
///     solution directly (build gate → detector re-run; no separate applier, §4.7.1).
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
    Func<string, int, CancellationToken, Task<(bool Ok, string Output)>>? build = null)
{
    private static readonly string[] SkipDirs = ["bin", "obj", ".git", ".vs", ".idea"];

    /// <summary>The compiler tool. Defaults to a real <c>dotnet build</c>; overridable for tests.</summary>
    private readonly Func<string, int, CancellationToken, Task<(bool Ok, string Output)>> _build
        = build ?? DotnetBuilder.BuildAsync;

    /// <param name="knownInstances">Ground-truth instances (the rated set), grouped internally by file.</param>
    /// <param name="runs">Trajectories per file (default 3).</param>
    /// <param name="maxInputTokenGuard">Heuristic token cap; over this the file is flagged as likely truncated.</param>
    /// <param name="trajectoryDir">Directory for the frozen per-trajectory artefacts.</param>
    /// <param name="sweepFiles">
    /// Optional full set of source files to process. When given (the whole corpus), files without a
    /// seeded instance contribute precision evidence — any detection on them is a scoreable spurious
    /// finding (§4.5.1). When null, only the files holding a seeded instance are processed.
    /// </param>
    public async Task RunAsync(
        IReadOnlyList<KnownInstance> knownInstances,
        int runs,
        IRunStore runStore,
        int maxInputTokenGuard,
        string trajectoryDir,
        TextWriter progress,
        CancellationToken ct,
        IReadOnlyList<string>? sweepFiles = null)
    {
        var knownByFile = knownInstances
            .GroupBy(k => Path.GetFullPath(k.FilePath), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g.ToList(), StringComparer.OrdinalIgnoreCase);

        var files = (sweepFiles is { Count: > 0 }
                ? sweepFiles.Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase)
                : knownByFile.Keys)
            .ToList();

        var corpusRoot  = Path.GetDirectoryName(Path.GetFullPath(solutionPath))!;
        var workingRoot = Path.Combine(Path.GetTempPath(), $"hybridlens-agentic-{Guid.NewGuid():N}");
        var workingSln  = Path.Combine(workingRoot, Path.GetFileName(solutionPath));

        var withInstances = files.Count(knownByFile.ContainsKey);
        progress.WriteLine(
            $"agentic: {files.Count} file(s) ({withInstances} with seeded instances), " +
            $"{knownInstances.Count} known instance(s), model={modelName}, runs={runs}, " +
            $"budget={iterationBudget}, prompt={PromptTemplate.AgenticVersion}");
        progress.WriteLine($"  working copy: {workingRoot}");
        Directory.CreateDirectory(trajectoryDir);

        var systemPrompt = PromptTemplate.BuildAgenticSystemPrompt(iterationBudget);

        CopyTree(corpusRoot, workingRoot);
        try
        {
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

                progress.WriteLine($"  [{fileNo}/{files.Count}] {Path.GetFileName(filePath)} " +
                                   $"(~{estTokens} tok{(truncated ? ", TRUNCATED-GUARD" : "")}, {known.Count} known)");

                for (var run = 1; run <= runs; run++)
                {
                    ct.ThrowIfCancellationRequested();

                    // Restore the target to pristine so each trajectory starts from the original file.
                    Directory.CreateDirectory(Path.GetDirectoryName(workingTarget)!);
                    File.Copy(filePath, workingTarget, overwrite: true);

                    try
                    {
                        var traj = await RunTrajectoryAsync(
                            systemPrompt, rel.Replace('\\', '/'), content, workingSln, workingTarget, ct);

                        var artefactRef = await WriteTrajectoryArtefactAsync(trajectoryDir, rel, run, traj, ct);

                        // Re-measure reads workingTarget (the final edited state) BEFORE the finally restore.
                        var records = await BuildRecordsAsync(filePath, workingTarget, known, run, truncated, traj, artefactRef, ct);
                        foreach (var rec in records)
                            await runStore.AppendAsync(rec, ct);

                        progress.WriteLine(
                            $"      run {run}: {traj.Iterations} build(s){(traj.BudgetExhausted ? ", BUDGET-EXHAUSTED" : "")}, " +
                            $"{traj.Findings.Count} finding(s), final build {(traj.BuildPassedFinal ? "ok" : "FAILED")}");
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
        string workingSln, string workingTarget, CancellationToken ct)
    {
        var userPrompt = PromptTemplate.BuildAgenticUserPrompt(relForPrompt, originalContent);
        var turns      = new List<ChatTurn> { new(ChatRole.User, userPrompt) };
        var builds     = new List<BuildAttempt>();

        var finalContent  = originalContent;     // last applied+built edit (== original if never edited)
        var iterations    = 0;                   // builds performed
        bool? lastBuildOk = null;                // verdict for finalContent's last build
        var declared      = new List<ParsedAgenticFinding>();
        var inputTokens   = 0;
        var outputTokens  = 0;
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
                response = await adapter.CompleteAsync(
                    new LlmConversation { SystemPrompt = systemPrompt, Turns = turns, PromptVersion = PromptTemplate.AgenticVersion },
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

            // Honour the latest declaration, including an explicit empty list (a deliberate retraction).
            // Only an ABSENT findings field leaves an earlier declaration intact.
            if (parsed.FindingsPresent)
                declared = parsed.Findings;

            if (parsed.Action == "complete" || string.IsNullOrWhiteSpace(parsed.EditedFile))
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
            builds.Add(new BuildAttempt(iterations, ok, Tail(output, 2000)));

            turns.Add(new ChatTurn(ChatRole.User,
                PromptTemplate.BuildAgenticBuildFeedback(iterations, iterationBudget, ok, Tail(output, 2000))));

            if (iterations >= iterationBudget)
                turns.Add(new ChatTurn(ChatRole.User,
                    "You have no build attempts remaining. Respond with action \"complete\" and your final findings."));
        }

        // Budget exhaustion (§4.8.1): the agent did not self-terminate and ran out of build attempts —
        // WITHOUT an API/parse/build error (those are recorded via Error, not as exhaustion).
        var exhausted = error is null && !completed && iterations >= iterationBudget;

        // The working file holds finalContent; it built iff the last edit built, or it was never edited
        // (the pristine corpus file compiles by construction).
        var buildPassedFinal = iterations == 0 || lastBuildOk == true;

        return new Trajectory(
            relForPrompt, systemPrompt, userPrompt, turns, builds, finalContent,
            iterations, exhausted, parseOk, buildPassedFinal, declared, inputTokens, outputTokens,
            error, errorMessage);
    }

    // ── Record construction ────────────────────────────────────────────────

    private async Task<List<RunRecord>> BuildRecordsAsync(
        string filePath, string workingTarget, List<KnownInstance> known, int runNumber, bool truncated,
        Trajectory traj, string artefactRef, CancellationToken ct)
    {
        var timestamp = DateTimeOffset.UtcNow;
        var records   = new List<RunRecord>();
        var matchedKeys = new HashSet<string>(StringComparer.Ordinal);

        // 1. Detection finding rows (recall + precision). Absence of a row for a known instance = a miss.
        foreach (var f in traj.Findings)
        {
            var match = Match(f, known);
            if (match is not null) matchedKeys.Add(match.InstanceKey);
            records.Add(FindingRecord(filePath, f, match, runNumber, timestamp, truncated, traj, artefactRef));
        }

        // 2. Verified-repair rows — score the FINAL edited solution against each seeded instance in the file.
        foreach (var inst in known)
        {
            ct.ThrowIfCancellationRequested();

            bool? buildPassed;
            IReadOnlyDictionary<string, double>? remeasured;
            VerifiedRepairOutcome ladder;

            if (!traj.BuildPassedFinal)
            {
                buildPassed = false; remeasured = null; ladder = VerifiedRepairOutcome.BuildFails;
            }
            else
            {
                var remeasure = await measurer.RemeasureAsync(inst.Type, workingTarget, inst.SymbolName, ct);
                buildPassed = true;
                ladder      = remeasure.StillTriggers ? VerifiedRepairOutcome.BuildsUnresolved : VerifiedRepairOutcome.Resolved;
                remeasured  = remeasure.StillTriggers ? remeasure.Metrics : null;
            }

            records.Add(VerifiedRecord(inst, runNumber, timestamp, truncated, traj, artefactRef,
                buildPassed, remeasured, ladder, recovered: matchedKeys.Contains(inst.InstanceKey)));
        }

        return records;
    }

    private RunRecord FindingRecord(
        string filePath, ParsedAgenticFinding f, KnownInstance? match,
        int runNumber, DateTimeOffset timestamp, bool truncated, Trajectory traj, string artefactRef)
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
            ContextLevel      = ContextLevel.Minimal,        // architecture is the discriminator, not context
            ModelName         = modelName,
            PromptVersion     = PromptTemplate.AgenticVersion,
            Architecture      = "agentic",
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
            DurationMs        = null,
            ParsedExplanation = f.Explanation,
            ParsedQualityImpact = string.IsNullOrWhiteSpace(f.QualityImpact) ? null : f.QualityImpact,
            ParsedSuggestedFix  = f.Remediation,
            ParsedRisks         = null,
            ExpectedQualityAttributes     = expected,
            LlmQualityAttributesMentioned = mentioned,
            QualityAttributeAlignment     = alignment,
            QualityAttributeNotes         = null,
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
        string artefactRef, bool? buildPassed, IReadOnlyDictionary<string, double>? remeasured,
        VerifiedRepairOutcome ladder, bool recovered)
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
            ContextLevel      = ContextLevel.Minimal,
            ModelName         = modelName,
            PromptVersion     = PromptTemplate.AgenticVersion,
            Architecture      = "agentic",
            ContextTruncated  = truncated,
            RawSystemPrompt   = traj.SystemPrompt,
            RawUserPrompt     = traj.UserPrompt,
            RawLlmOutput      = LastAssistant(traj),
            InputTokens       = traj.InputTokens,
            OutputTokens      = traj.OutputTokens,
            DurationMs        = null,
            // Verified-repair: the agent's own final solution is the repair (no separate applier, §4.7.1).
            ApplierModel             = null,
            ApplierPromptVersion     = null,
            RepairApplicable         = true,            // an agentic trajectory always produces source
            RepairUnapplicableReason = null,
            BuildPassed              = buildPassed,
            RemeasuredMetrics        = remeasured,
            VerifiedRepairLadder     = ladder,
            VerifiedRepairSuccess    = ladder == VerifiedRepairOutcome.Resolved,
            AgenticIterations      = traj.Iterations,
            AgenticBudgetExhausted = traj.BudgetExhausted,
            AgenticTrajectoryRef   = artefactRef,
            AgenticRecovered       = recovered,
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

            var action = root.TryGetProperty("action", out var a) ? a.GetString() ?? "" : "";
            action = action.Trim().ToLowerInvariant().Replace("-", "_").Replace(" ", "_");

            var edited = root.TryGetProperty("edited_file", out var e) && e.ValueKind == JsonValueKind.String
                ? e.GetString()
                : null;

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

    private sealed record BuildAttempt(int Attempt, bool Ok, string OutputTail);

    private sealed record Trajectory(
        string RelPath, string SystemPrompt, string UserPrompt,
        IReadOnlyList<ChatTurn> Turns, IReadOnlyList<BuildAttempt> Builds,
        string FinalContent, int Iterations, bool BudgetExhausted, bool ParseOk,
        bool BuildPassedFinal, IReadOnlyList<ParsedAgenticFinding> Findings,
        int InputTokens, int OutputTokens,
        ErrorStatus? Error, string? ErrorMessage);

    private async Task<string> WriteTrajectoryArtefactAsync(
        string trajectoryDir, string rel, int run, Trajectory traj, CancellationToken ct)
    {
        var safe = rel.Replace('\\', '_').Replace('/', '_');
        var path = Path.Combine(trajectoryDir, $"{safe}__run{run}.json");

        var artefact = new
        {
            file             = traj.RelPath,
            run,
            model            = modelName,
            prompt_version   = PromptTemplate.AgenticVersion,
            iteration_budget = iterationBudget,
            iterations       = traj.Iterations,
            budget_exhausted = traj.BudgetExhausted,
            parse_ok         = traj.ParseOk,
            error            = traj.Error?.ToString(),
            error_message    = traj.ErrorMessage,
            build_passed_final = traj.BuildPassedFinal,
            system_prompt    = traj.SystemPrompt,
            turns            = traj.Turns.Select(t => new { role = t.Role.ToString().ToLowerInvariant(), content = t.Content }),
            builds           = traj.Builds.Select(b => new { attempt = b.Attempt, ok = b.Ok, output = b.OutputTail }),
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
