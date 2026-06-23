using System.Diagnostics;
using System.Text.Json;
using HybridLens.Core.Abstractions;
using HybridLens.Core.Configuration;
using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Orchestrates the LLM stage of the hybrid pipeline.
///
/// One <see cref="LlmFinding"/> is produced per (finding × model × run-number).
/// Every attempt — success <i>and</i> failure — is appended to the optional
/// <see cref="IRunStore"/> as a <see cref="RunRecord"/> for thesis-grade traceability.
///
/// In-memory results returned to the caller deliberately contain only
/// run-number 1 per (finding × model), so existing output formatters stay
/// human-friendly. Repeated-run data lives in the run-store JSONL.
/// </summary>
public sealed class AnalysisPipeline(
    IContextBuilder contextBuilder,
    IReadOnlyDictionary<string, ILlmAdapter> adapters,
    ContextConfig contextConfig,
    PipelineConfig pipelineConfig)
{
    public async Task<IReadOnlyList<LlmFinding>> RunAsync(
        IReadOnlyList<Finding> findings,
        Severity minSeverity = Severity.Critical,
        int runs = 1,
        IRunStore? runStore = null,
        IReadOnlySet<string>? models = null,
        CancellationToken cancellationToken = default)
    {
        if (runs < 1) throw new ArgumentOutOfRangeException(nameof(runs));

        var eligible = Filter(findings, minSeverity);

        if (eligible.Count == 0)
            return [];

        // ── Static-analyser baseline path (H1 in the thesis) ─────────────────
        // No LLM call, no model loop. One deterministic record per finding.
        if (contextConfig.Level == ContextLevel.AnalyserOnly)
            return await RunBaselineAsync(eligible, runStore, cancellationToken);

        // Restrict generation to the requested models; the others stay configured for
        // their own roles (e.g. the verify-repair applier). Null/empty filter = all models.
        var activeAdapters = models is null || models.Count == 0
            ? adapters
            : adapters.Where(kv => models.Contains(kv.Key))
                      .ToDictionary(kv => kv.Key, kv => kv.Value, StringComparer.OrdinalIgnoreCase);

        if (activeAdapters.Count == 0)
            return [];

        // One work item per (finding × model × run-number).
        var workItems = eligible
            .SelectMany(f => activeAdapters.SelectMany(a =>
                Enumerable.Range(1, runs).Select(r =>
                    (Finding: f, ModelName: a.Key, Adapter: a.Value, RunNumber: r))))
            .Select((item, i) => (item.Finding, item.ModelName, item.Adapter, item.RunNumber, Index: i))
            .ToList();

        var results = new LlmFinding?[workItems.Count];

        await Parallel.ForEachAsync(
            workItems,
            new ParallelOptions
            {
                MaxDegreeOfParallelism = pipelineConfig.MaxParallelism,
                CancellationToken      = cancellationToken
            },
            async (item, ct) =>
            {
                var outcome = await ExecuteOneAsync(item.Finding, findings, item.ModelName, item.Adapter, item.RunNumber, ct);

                if (runStore is not null)
                    await runStore.AppendAsync(outcome.Record, ct);

                // Only run #1 feeds the in-memory formatter pipeline.
                if (item.RunNumber == 1 && outcome.Finding is not null)
                    results[item.Index] = outcome.Finding;
            });

        return results.OfType<LlmFinding>().ToList();
    }

    /// <summary>
    /// Generates one deterministic baseline record per finding for the H1 comparison.
    /// No LLM is invoked, no model loop runs. The baseline content is identical across
    /// re-runs of the same Finding, so we ignore the <c>runs</c> parameter here.
    /// </summary>
    private async Task<IReadOnlyList<LlmFinding>> RunBaselineAsync(
        IReadOnlyList<Finding> eligible,
        IRunStore? runStore,
        CancellationToken cancellationToken)
    {
        var results = new List<LlmFinding>(eligible.Count);

        foreach (var finding in eligible)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var (explanation, qualityImpact, remediation) = AnalyserBaseline.BuildFor(finding);
            var rawOutput = AnalyserBaseline.ComposeRawOutput(finding);
            var mentioned = QualityAttributeExtraction.ExtractMentioned(rawOutput);
            var alignment = QualityAttributeExtraction.ComputeAlignment(
                parsedOk: true, finding.ExpectedQualityAttributes, mentioned);

            var llmFinding = new LlmFinding
            {
                Finding                    = finding,
                ModelName                  = AnalyserBaseline.ModelName,
                Explanation                = explanation,
                Remediation                = remediation,
                QualityImpact              = qualityImpact,
                MentionedQualityAttributes = mentioned,
                RunNumber                  = 1,
                ContextLevel               = ContextLevel.AnalyserOnly,
                PromptVersion              = AnalyserBaseline.PromptVersion
            };

            var record = BuildRecord(
                runId:                      Guid.NewGuid().ToString("N"),
                timestamp:                  DateTimeOffset.UtcNow,
                runNumber:                  1,
                finding:                    finding,
                modelName:                  AnalyserBaseline.ModelName,
                promptVersion:              AnalyserBaseline.PromptVersion,
                rawSystem:                  string.Empty,
                rawUser:                    string.Empty,
                rawOutput:                  rawOutput,
                inputTokens:                null,
                outputTokens:               null,
                durationMs:                 0,
                explanation:                explanation,
                remediation:                remediation,
                parseStatus:                ParseStatus.Ok,
                errorStatus:                null,
                errorMessage:               null,
                qualityImpact:              qualityImpact,
                mentionedQualityAttributes: mentioned,
                qualityAttributeAlignment:  alignment);

            if (runStore is not null)
                await runStore.AppendAsync(record, cancellationToken);

            results.Add(llmFinding);
        }

        return results;
    }

    private async Task<(LlmFinding? Finding, RunRecord Record)> ExecuteOneAsync(
        Finding finding,
        IReadOnlyList<Finding> allFindings,
        string modelName,
        ILlmAdapter adapter,
        int runNumber,
        CancellationToken ct)
    {
        var timestamp = DateTimeOffset.UtcNow;
        var runId     = Guid.NewGuid().ToString("N");
        var sw        = Stopwatch.StartNew();

        // ── Build prompt (context-extraction phase) ──────────────────────────
        LlmRequest request;
        try
        {
            request = contextBuilder.Build(finding, allFindings, contextConfig);
        }
        catch (Exception ex)
        {
            sw.Stop();
            return (null, BuildRecord(
                runId, timestamp, runNumber, finding, modelName,
                promptVersion:  "unknown",
                rawSystem:      string.Empty,
                rawUser:        string.Empty,
                rawOutput:      null,
                inputTokens:    null,
                outputTokens:   null,
                durationMs:     sw.Elapsed.TotalMilliseconds,
                explanation:    null,
                remediation:    null,
                parseStatus:    ParseStatus.NotAttempted,
                errorStatus:    ErrorStatus.ContextExtractionFailure,
                errorMessage:   ex.Message));
        }

        // ── Call the model ───────────────────────────────────────────────────
        LlmResponse response;
        try
        {
            response = await adapter.CompleteAsync(request, ct);
        }
        catch (OperationCanceledException)
        {
            sw.Stop();
            return (null, BuildRecord(
                runId, timestamp, runNumber, finding, modelName,
                request.PromptVersion, request.SystemPrompt, request.UserPrompt,
                rawOutput: null, inputTokens: null, outputTokens: null,
                durationMs: sw.Elapsed.TotalMilliseconds,
                explanation: null, remediation: null,
                parseStatus: ParseStatus.NotAttempted,
                errorStatus: ErrorStatus.Cancelled,
                errorMessage: "operation cancelled"));
        }
        catch (Exception ex)
        {
            sw.Stop();
            await Console.Error.WriteLineAsync(
                $"  [llm-error] {modelName} / {finding.SymbolName} (run {runNumber}): {ex.Message}");
            return (null, BuildRecord(
                runId, timestamp, runNumber, finding, modelName,
                request.PromptVersion, request.SystemPrompt, request.UserPrompt,
                rawOutput: null, inputTokens: null, outputTokens: null,
                durationMs: sw.Elapsed.TotalMilliseconds,
                explanation: null, remediation: null,
                parseStatus: ParseStatus.NotAttempted,
                errorStatus: ClassifyApiError(ex),
                errorMessage: ex.Message));
        }

        sw.Stop();

        // ── Parse the structured response ────────────────────────────────────
        var parsed = ParseResponse(response.Content);

        // Quality-attribute extraction & alignment scoring.
        // Scan the full raw output so attributes mentioned in any section (explanation,
        // quality_impact, remediation) count toward the lexical match.
        var mentioned = QualityAttributeExtraction.ExtractMentioned(response.Content);
        var alignment = QualityAttributeExtraction.ComputeAlignment(
            parsed.Status == ParseStatus.Ok, finding.ExpectedQualityAttributes, mentioned);

        var llmFinding = new LlmFinding
        {
            Finding                    = finding,
            ModelName                  = modelName,
            Explanation                = parsed.Explanation ?? response.Content,
            Remediation                = parsed.Remediation ?? "Could not parse structured response.",
            QualityImpact              = parsed.QualityImpact ?? string.Empty,
            MentionedQualityAttributes = mentioned,
            RunNumber                  = runNumber,
            ContextLevel               = contextConfig.Level,
            PromptVersion              = request.PromptVersion
        };

        var record = BuildRecord(
            runId, timestamp, runNumber, finding, modelName,
            request.PromptVersion, request.SystemPrompt, request.UserPrompt,
            rawOutput:                 response.Content,
            inputTokens:               response.InputTokens,
            outputTokens:              response.OutputTokens,
            durationMs:                sw.Elapsed.TotalMilliseconds,
            explanation:               parsed.Explanation,
            qualityImpact:             parsed.QualityImpact,
            remediation:               parsed.Remediation,
            mentionedQualityAttributes: mentioned,
            qualityAttributeAlignment:  alignment,
            parseStatus:                parsed.Status,
            errorStatus:                parsed.Status == ParseStatus.Failed ? ErrorStatus.ParseFailure
                                        : string.IsNullOrWhiteSpace(response.Content) ? ErrorStatus.EmptyResponse
                                        : null,
            errorMessage:               parsed.Status == ParseStatus.Failed ? "structured-response parse failed"
                                        : string.IsNullOrWhiteSpace(response.Content) ? "empty response from model"
                                        : null);

        return (llmFinding, record);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private static List<Finding> Filter(IReadOnlyList<Finding> findings, Severity minSeverity)
        => findings.Where(f => f.Severity >= minSeverity).ToList();

    private RunRecord BuildRecord(
        string                  runId,
        DateTimeOffset          timestamp,
        int                     runNumber,
        Finding                 finding,
        string                  modelName,
        string                  promptVersion,
        string                  rawSystem,
        string                  rawUser,
        string?                 rawOutput,
        int?                    inputTokens,
        int?                    outputTokens,
        double?                 durationMs,
        string?                 explanation,
        string?                 remediation,
        ParseStatus             parseStatus,
        ErrorStatus?            errorStatus,
        string?                 errorMessage,
        string?                 qualityImpact              = null,
        IReadOnlyList<string>?  mentionedQualityAttributes = null,
        int?                    qualityAttributeAlignment  = null)
        => new()
        {
            RunId                         = runId,
            Timestamp                     = timestamp,
            RunNumber                     = runNumber,
            AntiPatternType               = finding.Type,
            FilePath                      = finding.FilePath,
            SymbolName                    = finding.SymbolName,
            Line                          = finding.Line,
            Severity                      = finding.Severity,
            Snippet                       = finding.Snippet,
            Metrics                       = finding.Metrics.Count > 0 ? finding.Metrics : null,
            ContextLevel                  = contextConfig.Level,
            ModelName                     = modelName,
            PromptVersion                 = promptVersion,
            Architecture                  = contextConfig.Level == ContextLevel.AnalyserOnly
                                                ? "analyser_only" : "hybrid",
            RawSystemPrompt               = rawSystem,
            RawUserPrompt                 = rawUser,
            RawLlmOutput                  = rawOutput,
            InputTokens                   = inputTokens,
            OutputTokens                  = outputTokens,
            DurationMs                    = durationMs,
            ParsedExplanation             = explanation,
            ParsedQualityImpact           = qualityImpact,
            ParsedSuggestedFix            = remediation,
            ParsedRisks                   = null,                                  // reserved for a future prompt revision
            ExpectedQualityAttributes     = finding.ExpectedQualityAttributes,
            LlmQualityAttributesMentioned = mentionedQualityAttributes,
            QualityAttributeAlignment     = qualityAttributeAlignment,
            QualityAttributeNotes         = null,                                  // populated by score_runs.py on second-rater review
            ParseStatus                   = parseStatus,
            ErrorStatus                   = errorStatus,
            ErrorMessage                  = errorMessage
        };

    /// <summary>Best-effort categorisation of API exceptions. Catches the common cases without taking SDK dependencies.</summary>
    private static ErrorStatus ClassifyApiError(Exception ex)
    {
        var msg = ex.Message?.ToLowerInvariant() ?? string.Empty;
        if (msg.Contains("token") && (msg.Contains("limit") || msg.Contains("exceeded") || msg.Contains("truncat")))
            return ErrorStatus.TokenLimitTruncation;
        if (msg.Contains("empty") || msg.Contains("no content"))
            return ErrorStatus.EmptyResponse;
        return ErrorStatus.ApiFailure;
    }

    private readonly record struct ParsedResponse(
        string?     Explanation,
        string?     QualityImpact,
        string?     Remediation,
        ParseStatus Status);

    private static ParsedResponse ParseResponse(string content)
    {
        try
        {
            var json = content.Trim();
            if (json.StartsWith("```"))
            {
                json = string.Join('\n', json.Split('\n').Skip(1));
                json = json[..json.LastIndexOf("```", StringComparison.Ordinal)].Trim();
            }

            using var doc   = JsonDocument.Parse(json);
            var explanation = doc.RootElement.TryGetProperty("explanation",    out var e) ? e.GetString() : string.Empty;
            var quality     = doc.RootElement.TryGetProperty("quality_impact", out var q) ? q.GetString() : null;
            var remediation = doc.RootElement.TryGetProperty("remediation",    out var r) ? r.GetString() : string.Empty;

            // explanation + remediation must be present for the response to count as Ok.
            // quality_impact is optional so v1.0.0 traces don't mass-fail when re-parsed.
            if (string.IsNullOrWhiteSpace(explanation) && string.IsNullOrWhiteSpace(remediation))
                return new ParsedResponse(null, null, null, ParseStatus.Failed);

            return new ParsedResponse(explanation, quality, remediation, ParseStatus.Ok);
        }
        catch
        {
            return new ParsedResponse(null, null, null, ParseStatus.Failed);
        }
    }

    // ── Quality-attribute extraction & alignment (Req: ISO/IEC 25010 mapping) ──

}
