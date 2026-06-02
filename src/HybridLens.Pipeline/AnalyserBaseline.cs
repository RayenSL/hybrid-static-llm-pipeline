using HybridLens.Core.Models;

namespace HybridLens.Pipeline;

/// <summary>
/// Generates deterministic "analyser-only" baseline records for the H1 comparison
/// (§4.4.1 of the thesis). The baseline is the static analyser's diagnostic message —
/// anti-pattern label, location, and a brief metric-based reason — without any
/// LLM-generated explanation, quality-impact discussion, or repair suggestion.
///
/// Raters evaluate baseline records under the same rubric (Appendix B) as the
/// hybrid (LLM-grounded) conditions; this allows quantitative comparison of how
/// much the LLM adds beyond what the analyser already provides.
///
/// Determinism: the same Finding always produces the same baseline text. This is
/// intentional — the baseline is not a stochastic process, so we generate one
/// record per Finding regardless of the --runs setting.
/// </summary>
public static class AnalyserBaseline
{
    public const string ModelName     = "static-analyser";
    public const string PromptVersion = "baseline-v1.0.0";

    /// <summary>
    /// Builds the three structured sections used downstream by the rater workflow.
    /// quality_impact and remediation are explicitly empty (with an honest note) —
    /// the baseline is, by definition, not the source of those claims.
    /// </summary>
    public static (string Explanation, string QualityImpact, string Remediation) BuildFor(Finding f)
    {
        var brief = f.Type switch
        {
            AntiPatternType.LongMethod        => BriefForLongMethod(f),
            AntiPatternType.GodClass          => BriefForGodClass(f),
            AntiPatternType.ObsoleteApiUsage  => BriefForObsoleteApi(f),
            _                                 => "Anti-pattern detected by the static analyser."
        };

        var explanation =
            $"[{f.Type}] {f.SymbolName} at {f.FilePath}:{f.Line}. {brief}";

        const string qualityImpact =
            "Quality impact: not provided by the static analyser.";

        const string remediation =
            "Remediation: not provided by the static analyser.";

        return (explanation, qualityImpact, remediation);
    }

    /// <summary>Composed raw output used for the <c>raw_llm_output</c> field of the experiment record.</summary>
    public static string ComposeRawOutput(Finding f)
    {
        var (explanation, qi, rem) = BuildFor(f);
        return $"{explanation}\n\n{qi}\n\n{rem}";
    }

    // ── Per-anti-pattern brief reasons (metric-grounded, single sentence) ────

    private static string BriefForLongMethod(Finding f)
    {
        var loc = MetricOrNull(f, "LinesOfCode");
        var cc  = MetricOrNull(f, "CyclomaticComplexity");
        if (loc is not null && cc is not null)
            return $"Method exceeds size and complexity thresholds (lines of code = {loc}, cyclomatic complexity = {cc}).";
        if (loc is not null)
            return $"Method exceeds the configured size threshold (lines of code = {loc}).";
        return "Method exceeds the configured size or complexity thresholds.";
    }

    private static string BriefForGodClass(Finding f)
    {
        var atfd = MetricOrNull(f, "ATFD");
        var wmc  = MetricOrNull(f, "WMC");
        var tcc  = MetricOrNull(f, "TCC");
        var parts = new List<string>();
        if (atfd is not null) parts.Add($"ATFD = {atfd}");
        if (wmc  is not null) parts.Add($"WMC = {wmc}");
        if (tcc  is not null) parts.Add($"TCC = {tcc}");

        return parts.Count > 0
            ? $"Class flagged by the Lanza & Marinescu God Class strategy ({string.Join(", ", parts)})."
            : "Class flagged by the Lanza & Marinescu God Class detection strategy.";
    }

    private static string BriefForObsoleteApi(Finding f)
    {
        return $"Usage of a deprecated or obsolete API symbol ({f.SymbolName}).";
    }

    private static string? MetricOrNull(Finding f, string key)
        => f.Metrics.TryGetValue(key, out var v) ? v.ToString("0.##") : null;
}
