using System.Text.Json;

namespace HybridLens.Pipeline;

internal readonly record struct ParsedAgenticFinding(
    string? AntiPattern, string? Symbol, int Line,
    string Explanation, string QualityImpact, string Remediation);

/// <param name="FindingsPresent">Whether the turn carried a "findings" array at all — distinguishes a
/// deliberate empty list (a retraction, which overwrites) from an absent field (which leaves the prior set).</param>
internal sealed record ParsedTurn(string Action, string? EditedFile, List<ParsedAgenticFinding> Findings, bool FindingsPresent);

/// <summary>Decodes the frozen iterative response contract without executing model actions.</summary>
internal static class AgenticResponseParser
{
    public static ParsedTurn? ParseTurn(string content)
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

}
