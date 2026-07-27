using System.Text.Json;
using HybridLens.Core.Models;
using HybridLens.Pipeline;

namespace HybridLens.CLI.Commands;

/// <summary>Loads the frozen Long Method/God Class instance set and detector metrics from analyzer JSONL.</summary>
internal static class FactorialCampaignInputLoader
{
    public static IReadOnlyList<FactorialCampaignSeed> Load(string path)
    {
        var order = new List<string>();
        var entries = new Dictionary<string, Entry>(StringComparer.Ordinal);
        foreach (var raw in File.ReadLines(path))
        {
            if (string.IsNullOrWhiteSpace(raw)) continue;
            JsonDocument document;
            try { document = JsonDocument.Parse(raw); }
            catch (JsonException) { continue; }
            using (document)
            {
                var root = document.RootElement;
                var type = NormaliseType(GetString(root, "anti_pattern_type"));
                var file = GetString(root, "file_path");
                var symbol = GetString(root, "symbol_name");
                if (type is null || file is null || symbol is null) continue;
                var line = GetInt(root, "line") ?? 0;
                var key = $"{file}::{symbol}::{line}";
                var severity = GetString(root, "severity")?.ToLowerInvariant() switch
                {
                    "critical" => Severity.Critical,
                    "warning" => Severity.Warning,
                    _ => Severity.Info
                };
                var snippet = GetString(root, "snippet");
                var metrics = GetMetrics(root);
                if (!entries.TryGetValue(key, out var existing))
                {
                    order.Add(key);
                    entries[key] = new Entry(type.Value, file, symbol, line, severity, snippet, metrics);
                }
                else if (existing.Metrics.Count == 0 && metrics.Count > 0)
                {
                    entries[key] = existing with
                    {
                        Metrics = metrics,
                        Snippet = existing.Snippet ?? snippet
                    };
                }
            }
        }

        return order.Select(key =>
        {
            var entry = entries[key];
            var known = KnownInstance.Create(
                entry.Type, entry.File, entry.Symbol, entry.Line, entry.Severity, entry.Snippet);
            var finding = new Finding
            {
                Type = entry.Type,
                Severity = entry.Severity,
                FilePath = entry.File,
                SymbolName = entry.Symbol,
                Line = entry.Line,
                Snippet = entry.Snippet,
                Metrics = entry.Metrics
            };
            return new FactorialCampaignSeed(known, finding);
        }).ToList();
    }

    private sealed record Entry(
        AntiPatternType Type,
        string File,
        string Symbol,
        int Line,
        Severity Severity,
        string? Snippet,
        Dictionary<string, double> Metrics);

    private static string? GetString(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static int? GetInt(JsonElement element, string name) =>
        element.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) ? number : null;

    private static Dictionary<string, double> GetMetrics(JsonElement element)
    {
        var metrics = new Dictionary<string, double>(StringComparer.Ordinal);
        if (element.TryGetProperty("metrics", out var value) && value.ValueKind == JsonValueKind.Object)
            foreach (var property in value.EnumerateObject())
                if (property.Value.TryGetDouble(out var number)) metrics[property.Name] = number;
        return metrics;
    }

    private static AntiPatternType? NormaliseType(string? raw)
    {
        var value = raw?.Replace(" ", "").Replace("_", "").Replace("-", "").ToLowerInvariant();
        return value switch
        {
            "godclass" => AntiPatternType.GodClass,
            "longmethod" => AntiPatternType.LongMethod,
            _ => null
        };
    }
}
