using System.Diagnostics;
using System.Text.Json;
using HybridLens.ContextBuilder;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Models;
using HybridLens.Core.QualityAttributes;

namespace HybridLens.Pipeline;

/// <summary>
/// Runs the LLM-only architecture arm (§4.4.1). Unlike the hybrid pipeline, the unit of
/// work is a whole source FILE: the frontier model receives the entire file with no
/// static-analysis grounding (prompt v1.2.0) and must self-detect anti-patterns. Each
/// reported finding is matched against the known instances by type + line-in-range OR
/// simple-symbol overlap (§4.5.1). Runs sequentially to respect the deployment's
/// tokens-per-minute limit.
/// </summary>
public sealed class LlmOnlyRunner(ILlmAdapter adapter, string modelName)
{
    /// <param name="knownInstances">Ground-truth instances (the rated set), grouped internally by file.</param>
    /// <param name="runs">Runs per file (default 3).</param>
    /// <param name="maxInputTokenGuard">Heuristic token cap; over this the input is flagged as likely truncated.</param>
    public async Task RunAsync(
        IReadOnlyList<KnownInstance> knownInstances,
        int runs,
        IRunStore runStore,
        int maxInputTokenGuard,
        TextWriter progress,
        CancellationToken ct)
    {
        var byFile = knownInstances
            .GroupBy(k => k.FilePath)
            .ToList();

        progress.WriteLine($"LLM-only: {byFile.Count} file(s), {knownInstances.Count} known instance(s), " +
                           $"model={modelName}, runs={runs}, prompt={PromptTemplate.LlmOnlyVersion}");

        var fileNo = 0;
        foreach (var fileGroup in byFile)
        {
            fileNo++;
            var filePath = fileGroup.Key;
            var known    = fileGroup.ToList();

            if (!File.Exists(filePath))
            {
                progress.WriteLine($"  [{fileNo}/{byFile.Count}] [skip] file not found: {filePath}");
                continue;
            }

            var content   = await File.ReadAllTextAsync(filePath, ct);
            var estTokens = content.Length / 4;                 // ~4 chars/token heuristic
            var truncated = estTokens > maxInputTokenGuard;
            var userPrompt = PromptTemplate.BuildLlmOnlyUserPrompt(filePath, content);

            progress.WriteLine($"  [{fileNo}/{byFile.Count}] {Path.GetFileName(filePath)} " +
                               $"(~{estTokens} tok{(truncated ? ", TRUNCATED-GUARD" : "")}, {known.Count} known)");

            for (var run = 1; run <= runs; run++)
            {
                ct.ThrowIfCancellationRequested();
                var records = await ExecuteFileRunAsync(filePath, userPrompt, known, run, truncated, ct);
                foreach (var rec in records)
                    await runStore.AppendAsync(rec, ct);
            }
        }
    }

    private async Task<IReadOnlyList<RunRecord>> ExecuteFileRunAsync(
        string filePath, string userPrompt, List<KnownInstance> known,
        int runNumber, bool truncated, CancellationToken ct)
    {
        var timestamp = DateTimeOffset.UtcNow;
        var sw = Stopwatch.StartNew();

        var request = new LlmRequest
        {
            SystemPrompt  = PromptTemplate.LlmOnlySystemPrompt,
            UserPrompt    = userPrompt,
            PromptVersion = PromptTemplate.LlmOnlyVersion
        };

        LlmResponse response;
        try
        {
            response = await adapter.CompleteAsync(request, ct);
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            sw.Stop();
            await Console.Error.WriteLineAsync($"    [llm-error] {Path.GetFileName(filePath)} run {runNumber}: {ex.Message}");
            return new[]
            {
                ErrorRecord(filePath, known, runNumber, timestamp, sw.Elapsed.TotalMilliseconds,
                            request, truncated, ClassifyApiError(ex), ex.Message)
            };
        }
        sw.Stop();

        var parsed = ParseArray(response.Content);
        if (parsed is null)
        {
            // Output present but not a usable JSON array.
            return new[]
            {
                ErrorRecord(filePath, known, runNumber, timestamp, sw.Elapsed.TotalMilliseconds,
                            request, truncated, ErrorStatus.ParseFailure, "LLM-only array parse failed",
                            rawOutput: response.Content,
                            inputTokens: response.InputTokens, outputTokens: response.OutputTokens)
            };
        }

        if (parsed.Count == 0)
        {
            // Valid empty list — model found nothing. All known in this file are recall misses;
            // no finding rows are written (absence of a match = miss in analysis).
            return Array.Empty<RunRecord>();
        }

        var records = new List<RunRecord>(parsed.Count);
        foreach (var f in parsed)
        {
            var match = Match(f, known);
            records.Add(FindingRecord(filePath, f, match, runNumber, timestamp,
                sw.Elapsed.TotalMilliseconds, request, response, truncated));
        }
        return records;
    }

    // ── Matching (§4.5.1) ──────────────────────────────────────────────────────

    private static KnownInstance? Match(ParsedLlmFinding f, List<KnownInstance> known)
    {
        var type = NormaliseType(f.AntiPattern);
        if (type is null) return null;

        foreach (var k in known)
        {
            if (k.Type != type) continue;
            var lineInRange   = f.Line >= k.Line && f.Line <= k.EndLine;
            var symbolOverlap = SimpleNameOverlap(f.Symbol, k.SymbolName);
            if (lineInRange || symbolOverlap)
                return k;
        }
        return null;
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
        // Drop namespace/type qualifiers and any parameter list.
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
            "godclass"                              => AntiPatternType.GodClass,
            "longmethod"                            => AntiPatternType.LongMethod,
            "obsoleteapiusage" or "obsoleteapi"     => AntiPatternType.ObsoleteApiUsage,
            _                                       => null
        };
    }

    // ── Parsing ─────────────────────────────────────────────────────────────────

    private readonly record struct ParsedLlmFinding(
        string? AntiPattern, string? Symbol, int Line,
        string Explanation, string QualityImpact, string Remediation);

    private static List<ParsedLlmFinding>? ParseArray(string content)
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
            if (doc.RootElement.ValueKind != JsonValueKind.Array)
                return null;

            var list = new List<ParsedLlmFinding>();
            foreach (var el in doc.RootElement.EnumerateArray())
            {
                if (el.ValueKind != JsonValueKind.Object) continue;

                var ap = el.TryGetProperty("anti_pattern", out var a) ? a.GetString() : null;

                string? symbol = null;
                var line = 0;
                if (el.TryGetProperty("location", out var loc) && loc.ValueKind == JsonValueKind.Object)
                {
                    symbol = loc.TryGetProperty("symbol", out var s) ? s.GetString() : null;
                    if (loc.TryGetProperty("line", out var ln) && ln.TryGetInt32(out var lv)) line = lv;
                }

                list.Add(new ParsedLlmFinding(
                    ap, symbol, line,
                    el.TryGetProperty("explanation",    out var e) ? e.GetString() ?? "" : "",
                    el.TryGetProperty("quality_impact", out var q) ? q.GetString() ?? "" : "",
                    el.TryGetProperty("remediation",    out var r) ? r.GetString() ?? "" : ""));
            }
            return list;
        }
        catch
        {
            return null;
        }
    }

    // ── Record construction ───────────────────────────────────────────────────

    private RunRecord FindingRecord(
        string filePath, ParsedLlmFinding f, KnownInstance? match,
        int runNumber, DateTimeOffset timestamp, double durationMs,
        LlmRequest request, LlmResponse response, bool truncated)
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
            PromptVersion     = PromptTemplate.LlmOnlyVersion,
            Architecture      = "llm_only",
            LlmReportedSymbol = f.Symbol,
            LlmReportedLine   = f.Line,
            MatchedInstanceId = match?.InstanceKey,
            IsSpurious        = isSpurious,
            ContextTruncated  = truncated,
            RawSystemPrompt   = request.SystemPrompt,
            RawUserPrompt     = request.UserPrompt,
            RawLlmOutput      = response.Content,
            InputTokens       = response.InputTokens,
            OutputTokens      = response.OutputTokens,
            DurationMs        = durationMs,
            ParsedExplanation = f.Explanation,
            ParsedQualityImpact = string.IsNullOrWhiteSpace(f.QualityImpact) ? null : f.QualityImpact,
            ParsedSuggestedFix  = f.Remediation,
            ParsedRisks         = null,
            ExpectedQualityAttributes     = expected,
            LlmQualityAttributesMentioned = mentioned,
            QualityAttributeAlignment     = alignment,
            QualityAttributeNotes         = null,
            ParseStatus       = ParseStatus.Ok,
            ErrorStatus       = null,
            ErrorMessage      = null
        };
    }

    private RunRecord ErrorRecord(
        string filePath, List<KnownInstance> known, int runNumber, DateTimeOffset timestamp,
        double durationMs, LlmRequest request, bool truncated,
        ErrorStatus errorStatus, string errorMessage,
        string? rawOutput = null, int? inputTokens = null, int? outputTokens = null)
        => new()
        {
            RunId             = Guid.NewGuid().ToString("N"),
            Timestamp         = timestamp,
            RunNumber         = runNumber,
            AntiPatternType   = known.Count > 0 ? known[0].Type : AntiPatternType.GodClass, // placeholder for error row
            FilePath          = filePath,
            SymbolName        = "<llm-only-file>",
            Line              = 0,
            Severity          = Severity.Warning,
            ContextLevel      = ContextLevel.Minimal,
            ModelName         = modelName,
            PromptVersion     = PromptTemplate.LlmOnlyVersion,
            Architecture      = "llm_only",
            ContextTruncated  = truncated,
            RawSystemPrompt   = request.SystemPrompt,
            RawUserPrompt     = request.UserPrompt,
            RawLlmOutput      = rawOutput,
            InputTokens       = inputTokens,
            OutputTokens      = outputTokens,
            DurationMs        = durationMs,
            ParseStatus       = ParseStatus.NotAttempted,
            ErrorStatus       = errorStatus,
            ErrorMessage      = errorMessage
        };

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
